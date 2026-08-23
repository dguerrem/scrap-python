"""
Scheduler: cuándo se puede enviar, cuánto y con qué ritmo.

El intervalo define el **ritmo** y el tope diario define el **volumen**. Son
dos frenos independientes a propósito: el ritmo evita parecer un robot, el
tope protege la reputación del dominio.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    MADRID = ZoneInfo("Europe/Madrid")
except Exception:  # pragma: no cover - sistemas sin base de datos de husos
    MADRID = timezone(timedelta(hours=1))

from src.crm.db import update_lead_stage
from src.mailer import config, store
from src.mailer.sender import EnvioFallido, enviar

log = logging.getLogger(__name__)

# Rampa de calentamiento: (días desde el inicio, tope diario)
RAMPA = [(0, 10), (3, 15), (7, 25), (14, 35), (21, None)]  # None = tope_maximo


# ======================================================
# TIEMPO Y VENTANA
# ======================================================

def ahora_madrid() -> datetime:
    return datetime.now(timezone.utc).astimezone(MADRID)


def ventana_abierta(momento: datetime | None = None) -> tuple:
    """(abierta, motivo). L-V dentro del horario configurado, hora española.

    El cron de GitHub es UTC y España cambia de huso dos veces al año, así que
    la decisión se toma aquí y no en el YAML: el horario de verano se resuelve
    solo, para siempre.
    """
    if config.fast_clock() or config.force_window():
        return True, "ventana ignorada (modo prueba)"

    momento = momento or ahora_madrid()
    if momento.weekday() >= 5:
        return False, "fin de semana"

    inicio = store.get_int("ventana_inicio", 8)
    fin = store.get_int("ventana_fin", 15)
    if not (inicio <= momento.hour < fin):
        return False, f"fuera de horario ({inicio}:00-{fin}:00, son las {momento.hour}:00)"
    return True, ""


def dia_de_warmup() -> int | None:
    """Días transcurridos desde el inicio del calentamiento."""
    inicio = store.get_setting("warmup_start_date", "")
    if not inicio:
        return None
    fecha = store.a_fecha(inicio) or store.a_fecha(inicio + " 00:00:00")
    if not fecha:
        return None
    return max(0, (store.ahora() - fecha).days)


def _tope_de_rampa(dias: int) -> int:
    maximo = store.get_int("tope_maximo", 45)
    tope = RAMPA[0][1]
    for desde, valor in RAMPA:
        if dias >= desde:
            tope = maximo if valor is None else valor
    return min(tope, maximo)


def tasa_fallos(dias: int = 7) -> float:
    """Proporción de envíos fallidos en los últimos N días."""
    desde = store.ahora() - timedelta(days=dias)
    logs = [l for l in store.ultimos_logs(500)
            if (store.a_fecha(l["created_at"]) or store.ahora()) >= desde]
    enviados = sum(1 for l in logs if l["evento"] == "sent")
    fallidos = sum(1 for l in logs if l["evento"] == "failed")
    total = enviados + fallidos
    return (fallidos / total) if total else 0.0


def tope_diario() -> int:
    """Tope de hoy: manual si lo hay, si no la rampa, con freno por fallos."""
    manual = store.get_setting("tope_manual", "").strip()
    if manual:
        try:
            return max(0, int(manual))
        except ValueError:
            pass

    dias = dia_de_warmup()
    if dias is None:
        return RAMPA[0][1]  # aún no se ha activado: arranca por lo más bajo

    tope = _tope_de_rampa(dias)
    # Freno automático: si la cosa va mal, la rampa no sigue subiendo.
    if tasa_fallos() > 0.05:
        tope = min(tope, _tope_de_rampa(max(0, dias - 7)))
    return tope


def enviados_hoy() -> int:
    """Envíos del día natural español (el tope es diario, no por ventana)."""
    hoy = ahora_madrid().replace(hour=0, minute=0, second=0, microsecond=0)
    desde = hoy.astimezone(timezone.utc).replace(tzinfo=None)
    return store.enviados_entre(desde, desde + timedelta(days=1))


# ======================================================
# RITMO
# ======================================================

def _proximo_hueco() -> datetime:
    minimo = store.get_int("intervalo_min_min", 5)
    maximo = store.get_int("intervalo_max_min", 15)
    if maximo < minimo:
        maximo = minimo
    salto = random.randint(minimo, maximo)
    unidad = timedelta(seconds=salto) if config.fast_clock() else timedelta(minutes=salto)
    return store.ahora() + unidad


def _programar_siguiente():
    store.set_setting("next_send_at", store.a_texto(_proximo_hueco()))


def toca_enviar() -> tuple:
    """(sí/no, motivo) según el hueco aleatorio programado."""
    siguiente = store.a_fecha(store.get_setting("next_send_at", ""))
    if siguiente is None:
        return True, ""
    if store.ahora() >= siguiente:
        return True, ""
    faltan = siguiente - store.ahora()
    return False, f"toca en {int(faltan.total_seconds() // 60)} min"


# ======================================================
# ESTADO (para la UI y para --status)
# ======================================================

def estado() -> dict:
    activo = store.get_setting("activo", "0") == "1"
    abierta, motivo_ventana = ventana_abierta()
    puede, motivo_hueco = toca_enviar()
    dias = dia_de_warmup()
    conteo = store.contar_cola()
    return {
        "activo": activo,
        "dia_warmup": dias,
        "tope_diario": tope_diario(),
        "enviados_hoy": enviados_hoy(),
        "ventana_abierta": abierta,
        "motivo_ventana": motivo_ventana,
        "toca_enviar": puede,
        "motivo_hueco": motivo_hueco,
        "next_send_at": store.get_setting("next_send_at", ""),
        "pendientes": conteo.get("pending", 0),
        "fallidos": conteo.get("failed", 0),
        "enviados_total": conteo.get("sent", 0),
        "ultimo_envio": store.ultimo_envio(),
        "tasa_fallos": tasa_fallos(),
        "modos_prueba": config.modo_prueba_activo(),
    }


def activar(encendido: bool):
    """Enciende o apaga el mailer. Al encender por primera vez arranca la rampa."""
    store.set_setting("activo", "1" if encendido else "0")
    if encendido and not store.get_setting("warmup_start_date", "").strip():
        store.set_setting("warmup_start_date", store.a_texto(store.ahora()))


# ======================================================
# TICK — procesa como máximo un envío
# ======================================================

def tick(forzar: bool = False) -> dict:
    """Un intento de envío. Idempotente y sin estado propio: todo vive en BD.

    `forzar` salta los frenos de ritmo y horario (botón "Enviar 1 ahora"),
    pero **nunca** el ledger ni la supresión.
    """
    store.asegurar_esquema()
    store.liberar_atascados()

    if not forzar:
        if store.get_setting("activo", "0") != "1":
            return {"accion": "nada", "motivo": "mailer apagado"}

        abierta, motivo = ventana_abierta()
        if not abierta:
            store.log("window_closed", motivo)
            return {"accion": "nada", "motivo": motivo}

        puede, motivo = toca_enviar()
        if not puede:
            return {"accion": "nada", "motivo": motivo}

        tope = tope_diario()
        hoy = enviados_hoy()
        if hoy >= tope:
            store.log("cap_reached", f"{hoy}/{tope}")
            return {"accion": "nada", "motivo": f"tope diario alcanzado ({hoy}/{tope})"}

    item = store.claim()
    if not item:
        return {"accion": "nada", "motivo": "cola vacía"}

    store.log("claimed", item["destinatario"], item["id"])

    # Re-check tras el claim: entre el encolado y ahora el dominio puede haber
    # entrado en el ledger (otro lead de la misma clínica) o en supresión.
    if store.en_ledger(item["dominio"]) or store.en_supresion(item["dominio"]):
        store.marcar(item["id"], "skipped", "dominio ya contactado o suprimido")
        store.log("skipped", item["dominio"], item["id"])
        return {"accion": "skipped", "dominio": item["dominio"]}

    # El ledger se escribe ANTES de enviar. Si el envío se cae a medias se
    # pierde un correo, pero no se llama dos veces a la misma puerta.
    if not store.registrar_ledger(item["dominio"], item["destinatario"], item["lead_id"]):
        store.marcar(item["id"], "skipped", "carrera con otro envío")
        store.log("skipped", "ledger ocupado", item["id"])
        return {"accion": "skipped", "dominio": item["dominio"]}

    try:
        detalle = enviar(
            item["destinatario"], item["asunto"],
            item["cuerpo_texto"], item["cuerpo_html"], item["id"],
        )
    except EnvioFallido as e:
        store.marcar(item["id"], "failed", str(e))
        store.log("failed", str(e), item["id"])
        _programar_siguiente()
        return {"accion": "failed", "error": str(e), "dominio": item["dominio"]}

    store.marcar(item["id"], "sent")
    store.log("sent", detalle, item["id"])
    if item["lead_id"]:
        try:
            update_lead_stage(item["lead_id"], "Contactado")
        except Exception as e:  # no romper el envío por un fallo de CRM
            log.warning("No se pudo mover el lead: %s", e)

    _programar_siguiente()
    return {"accion": "sent", "detalle": detalle, "dominio": item["dominio"]}
