"""
Autonomía: cuántos contactos quedan, cuándo se agotan y avisos proactivos.

Responde a la pregunta operativa de verdad: **"¿cuándo me quedo sin contactos
y dónde tengo que scrapear?"**
"""

from __future__ import annotations

import logging
from datetime import timedelta

from src.crm.db import get_conn
from src.mailer import config, store, templates
from src.mailer.sender import EnvioFallido, enviar

log = logging.getLogger(__name__)


def _email_de(lead: dict) -> str:
    """Se prefiere siempre el directo al genérico."""
    return (lead.get("email_directo") or lead.get("email_generico") or "").strip()


def contactables() -> list:
    """Leads con email cuyo dominio no está gastado ni vetado ni en cola."""
    conn = get_conn()
    leads = conn.execute(
        "SELECT id, nombre, ciudad, perfil_origen, email_directo, email_generico "
        "FROM leads WHERE (email_directo != '' AND email_directo IS NOT NULL "
        "   OR email_generico != '' AND email_generico IS NOT NULL) "
        "   AND etapa != 'Descartado'"
    ).fetchall()
    gastados = {
        r["dominio"] for r in conn.execute("SELECT dominio FROM email_ledger").fetchall()
    }
    vetados = {
        r["dominio"] for r in conn.execute("SELECT dominio FROM email_suppression").fetchall()
    }
    en_cola = {
        r["dominio"] for r in conn.execute(
            "SELECT dominio FROM email_queue WHERE estado IN ('pending', 'sending')"
        ).fetchall()
    }
    conn.close()

    fuera = gastados | vetados | en_cola
    salida, vistos = [], set()
    for row in leads:
        lead = dict(row)
        email = _email_de(lead)
        dominio = store.dominio_de(email)
        # Para genéricos la clave es el email; evita banear gmail.com entero.
        clave = store.clave_unica(email)
        if not dominio or clave in fuera or clave in vistos:
            continue
        vistos.add(clave)
        lead["email"] = email
        lead["dominio"] = dominio
        salida.append(lead)
    return salida


def resumen() -> dict:
    """Stock, ritmo y días de autonomía, con desglose por ciudad y perfil."""
    from src.mailer import scheduler

    disponibles = contactables()
    tope = scheduler.tope_diario()

    por_ciudad, por_perfil = {}, {}
    for lead in disponibles:
        ciudad = lead.get("ciudad") or "(sin ciudad)"
        perfil = lead.get("perfil_origen") or "(sin perfil)"
        por_ciudad[ciudad] = por_ciudad.get(ciudad, 0) + 1
        por_perfil[perfil] = por_perfil.get(perfil, 0) + 1

    # Ciudades que ya se trabajaron pero se han quedado sin nadie a quien escribir
    conn = get_conn()
    todas = {
        r["ciudad"] for r in conn.execute(
            "SELECT DISTINCT ciudad FROM leads WHERE ciudad != ''"
        ).fetchall()
    }
    conn.close()
    agotadas = sorted(c for c in todas if por_ciudad.get(c, 0) == 0)

    dias = (len(disponibles) / tope) if tope else 0
    return {
        "contactables": len(disponibles),
        "tope_diario": tope,
        "dias_autonomia": round(dias, 1),
        "por_ciudad": dict(sorted(por_ciudad.items(), key=lambda x: -x[1])),
        "por_perfil": dict(sorted(por_perfil.items(), key=lambda x: -x[1])),
        "ciudades_agotadas": agotadas,
        "en_cola": store.contar_cola().get("pending", 0),
    }


# ======================================================
# ENCOLADO
# ======================================================

def encolar_leads(leads: list, plantilla: dict | None = None) -> dict:
    """Renderiza y encola una lista de leads. Devuelve el recuento."""
    plantilla = plantilla or store.plantilla_activa()
    if not plantilla:
        raise ValueError("No hay ninguna plantilla activa.")

    firma_texto = store.get_setting("firma_texto", "")
    firma_html = store.get_setting("firma_html", "")

    encolados = saltados = 0
    for lead in leads:
        email = lead.get("email") or _email_de(lead)
        if not email:
            saltados += 1
            continue
        asunto, texto, html = templates.render(plantilla, lead, firma_texto, firma_html)
        if store.encolar(lead["id"], email, asunto, texto, html):
            encolados += 1
        else:
            saltados += 1
    return {"encolados": encolados, "saltados": saltados}


def previsualizar(lead: dict, plantilla: dict | None = None) -> tuple:
    plantilla = plantilla or store.plantilla_activa()
    if not plantilla:
        raise ValueError("No hay ninguna plantilla activa.")
    return templates.render(
        plantilla, lead,
        store.get_setting("firma_texto", ""),
        store.get_setting("firma_html", ""),
    )


# ======================================================
# AVISOS
# ======================================================

def _destinatarios_aviso() -> list:
    crudo = store.get_setting("aviso_emails", "")
    return [d.strip() for d in crudo.replace(";", ",").split(",") if d.strip()]


def _en_cooldown(clave: str, horas: int = 24) -> bool:
    ultimo = store.a_fecha(store.get_setting(clave, ""))
    if not ultimo:
        return False
    return (store.ahora() - ultimo) < timedelta(hours=horas)


def _avisar(asunto: str, cuerpo: str, clave_cooldown: str) -> bool:
    destinos = _destinatarios_aviso()
    if not destinos:
        return False
    html = "<pre style='font-family:Arial,sans-serif'>" + cuerpo + "</pre>"
    enviado = False
    for destino in destinos:
        try:
            enviar(destino, asunto, cuerpo, html, queue_id="aviso")
            enviado = True
        except EnvioFallido as e:
            log.warning("No se pudo enviar el aviso a %s: %s", destino, e)
    if enviado:
        store.set_setting(clave_cooldown, store.a_texto(store.ahora()))
        store.log("aviso", asunto)
    return enviado


def revisar_avisos() -> list:
    """Comprueba stock bajo y silencio prolongado. Devuelve los avisos emitidos."""
    emitidos = []

    umbral = store.get_int("aviso_umbral_dias", 3)
    datos = resumen()
    if datos["dias_autonomia"] < umbral and not _en_cooldown("aviso_ultimo"):
        agotadas = ", ".join(datos["ciudades_agotadas"]) or "ninguna"
        cuerpo = (
            f"Quedan {datos['contactables']} contactos disponibles.\n"
            f"Al ritmo actual de {datos['tope_diario']}/día son "
            f"{datos['dias_autonomia']} días.\n\n"
            f"Ciudades agotadas: {agotadas}\n\n"
            "Toca lanzar un scrap nuevo o bajar los filtros de reseñas."
        )
        if _avisar("PsycoLead: te quedas sin contactos", cuerpo, "aviso_ultimo"):
            emitidos.append("stock_bajo")

    # Heartbeat: el mailer encendido y sin enviar nada en 48 h laborables es
    # síntoma de cron apagado, App Password revocada o cuenta suspendida.
    if store.get_setting("activo", "0") == "1" and not _en_cooldown("heartbeat_ultimo"):
        ultimo = store.ultimo_envio()
        silencio = (store.ahora() - ultimo) if ultimo else None
        if silencio and silencio > timedelta(hours=48) and datos["contactables"]:
            cuerpo = (
                f"El mailer está activo pero no envía nada desde {ultimo} UTC.\n\n"
                "Causas posibles:\n"
                "- El cron de GitHub Actions se desactivó (pasan 60 días sin commits)\n"
                "- La contraseña de aplicación de Google fue revocada\n"
                "- La cuenta de Google está suspendida\n\n"
                f"Hay {datos['contactables']} contactos esperando."
            )
            if _avisar("PsycoLead: el mailer lleva 48h en silencio", cuerpo,
                       "heartbeat_ultimo"):
                emitidos.append("heartbeat")

    return emitidos
