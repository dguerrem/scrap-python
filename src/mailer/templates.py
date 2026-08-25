"""
Plantillas: renderizado, firma y pie de baja.

Reglas de contenido que no se negocian:
  · El copy se dirige a la **clínica** (`{nombre}`), nunca al director.
    Medido en producción, el email acierta un 90-95 % y el director bastante
    menos: a veces devuelve el propio nombre del negocio como si fuera una
    persona. Un "Hola Centro de Psicología Alameda" delata al robot.
  · Todo mensaje lleva pie de baja (art. 22 LSSI + art. 14 RGPD) y además
    mejora la entregabilidad.
"""

from __future__ import annotations

import html as _html
import re

# Variables permitidas en asunto y cuerpo. `director` queda fuera a propósito.
VARIABLES = ("nombre", "ciudad")

PIE_BAJA = (
    'Te escribo porque encontré los datos de contacto de tu clínica en su web.\n'
    'Si no quieres recibir nada más, responde "BAJA" y no volveré a escribirte.'
)

# Plantilla mínima para las pruebas en local. El copy de verdad se redacta
# aparte (6.7 del README).
PLANTILLA_PRUEBA = {
    "nombre": "Correo frio v2",
    "asunto": "Mejorar la gestión de {nombre}",
    "cuerpo": (
        "Hola, equipo de {nombre}:\n\n"
        "Somos el equipo de PsycoERP. Hemos desarrollado este software para ayudar "
        "a clínicas de psicología a reducir el tiempo dedicado a su gestión "
        "diaria.\n\n"
        "PsycoERP centraliza las citas y bonos, los recordatorios por WhatsApp, "
        "los historiales clínicos y el control de ingresos por profesional. Se "
        "adapta a la forma de trabajar de cada equipo y se instala en un servidor "
        "propio, para que la clínica mantenga el control de sus datos sin depender "
        "de plataformas de terceros.\n\n"
        "Me gustaría saber si este enfoque podría ayudaros a liberar horas de "
        "trabajo administrativo.\n\n"
        "Si os encaja, podéis responder a este correo y os contamos más.\n\n"
        "Un saludo,\n\n"
        "Equipo de PsycoERP\n"
        "https://psycoerp.es"
    ),
}


class PlantillaInvalida(ValueError):
    pass


def variables_usadas(texto: str) -> set:
    return set(re.findall(r"\{(\w+)\}", texto or ""))


def validar(asunto: str, cuerpo: str) -> list:
    """Devuelve la lista de problemas. Vacía = se puede guardar."""
    problemas = []

    if not (asunto or "").strip():
        problemas.append("El asunto no puede estar vacío.")
    if not (cuerpo or "").strip():
        problemas.append("El cuerpo no puede estar vacío.")

    desconocidas = variables_usadas(f"{asunto} {cuerpo}") - set(VARIABLES)
    if "director" in desconocidas:
        problemas.append(
            "{director} no se puede usar en el envío automático: el dato falla "
            "demasiado y arruina el primer contacto. Usa {nombre}."
        )
        desconocidas.discard("director")
    if desconocidas:
        problemas.append(
            "Variables que no existen: "
            + ", ".join("{%s}" % v for v in sorted(desconocidas))
            + f". Disponibles: " + ", ".join("{%s}" % v for v in VARIABLES)
        )

    return problemas


def _rellenar(texto: str, lead: dict) -> str:
    valores = {
        "nombre": (lead.get("nombre") or "").strip(),
        "ciudad": (lead.get("ciudad") or "").strip(),
    }
    salida = texto or ""
    for clave, valor in valores.items():
        salida = salida.replace("{%s}" % clave, valor)
    return salida


def _a_html(texto: str) -> str:
    """Texto plano → HTML sencillo. Se escapa: el nombre viene de la web."""
    escapado = _html.escape(texto).replace("\n", "<br>")
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;'
        'color:#222;line-height:1.6">' + escapado + "</div>"
    )


def render(plantilla: dict, lead: dict, firma_texto: str = "",
           firma_html: str = "") -> tuple:
    """Devuelve (asunto, cuerpo_texto, cuerpo_html) listos para enviar."""
    problemas = validar(plantilla.get("asunto", ""), plantilla.get("cuerpo", ""))
    if problemas:
        raise PlantillaInvalida("; ".join(problemas))

    asunto = _rellenar(plantilla["asunto"], lead)
    cuerpo = _rellenar(plantilla["cuerpo"], lead)

    partes_texto = [cuerpo.rstrip()]
    if firma_texto.strip():
        partes_texto.append(firma_texto.rstrip())
    # El pie de baja va siempre el último y lo añade el motor, no la plantilla:
    # así no se puede olvidar ni borrar desde la UI.
    partes_texto.append("--\n" + PIE_BAJA)
    texto = "\n\n".join(partes_texto)

    partes_html = [_a_html(cuerpo.rstrip())]
    if firma_html.strip():
        partes_html.append(firma_html)
    elif firma_texto.strip():
        partes_html.append(_a_html(firma_texto))
    partes_html.append(
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;'
        'color:#888;line-height:1.5;margin-top:16px;border-top:1px solid #eee;'
        'padding-top:8px">' + _html.escape(PIE_BAJA).replace("\n", "<br>") + "</div>"
    )
    html = "\n".join(partes_html)

    return asunto, texto, html
