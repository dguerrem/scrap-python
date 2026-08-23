"""
Construcción del mensaje y envío por SMTP.

Modos de prueba (variables de entorno, ver 6.6 del README):
  EMAIL_DRY_RUN=1                → no envía; escribe .eml en data/emails_out/
  EMAIL_REDIRECT_TO=tu@mail.com  → envía de verdad, todo a esa dirección
"""

from __future__ import annotations

import logging
import re
import smtplib
import socket
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from src.mailer import config

log = logging.getLogger(__name__)


class EnvioFallido(Exception):
    """Error recuperable: el email vuelve a la cola o se marca como fallido."""


def _nombre_fichero(destinatario: str, queue_id) -> str:
    limpio = re.sub(r"[^a-zA-Z0-9._-]", "_", destinatario or "sin_destinatario")
    return f"{queue_id or 'x'}_{limpio}.eml"


def construir(destinatario: str, asunto: str, texto: str, html: str,
              queue_id=None) -> EmailMessage:
    """Mensaje multipart/alternative (texto + HTML).

    Enviar sólo HTML penaliza en los filtros antispam, así que las dos
    versiones van siempre.
    """
    cfg = config.smtp_config()
    remitente = cfg["user"] or "sin-configurar@ejemplo.local"
    dominio_remitente = remitente.split("@")[-1]

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["Date"] = formatdate(localtime=True)
    msg["From"] = formataddr((cfg["from_name"], remitente))
    if cfg.get("reply_to") or remitente:
        msg["Reply-To"] = cfg.get("reply_to") or remitente
    msg["Message-ID"] = make_msgid(domain=dominio_remitente)

    # Gmail y Outlook puntúan mejor a quien ofrece una baja en un solo clic,
    # y el pie de texto por sí solo no cuenta: tiene que ir en la cabecera.
    msg["List-Unsubscribe"] = f"<mailto:{remitente}?subject=BAJA>"

    redirigido = config.redirect_to()
    if redirigido:
        # El destinatario real se conserva para poder auditar la prueba.
        msg["To"] = redirigido
        msg["X-Original-To"] = destinatario
    else:
        msg["To"] = destinatario

    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")
    return msg


def enviar(destinatario: str, asunto: str, texto: str, html: str,
           queue_id=None) -> str:
    """Envía (o simula) el mensaje. Devuelve una descripción del resultado.

    Lanza EnvioFallido si el envío real no sale.
    """
    msg = construir(destinatario, asunto, texto, html, queue_id)

    if config.dry_run():
        config.OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        destino = config.OUTBOX_DIR / _nombre_fichero(destinatario, queue_id)
        destino.write_bytes(bytes(msg))
        return f"dry-run: {destino.name}"

    listo, motivo = config.smtp_listo()
    if not listo:
        raise EnvioFallido(f"SMTP sin configurar ({motivo})")

    cfg = config.smtp_config()
    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(cfg["user"], cfg["password"])
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise EnvioFallido(
            "Google rechazó las credenciales. Revisa que la contraseña de "
            f"aplicación siga activa. ({e.smtp_code})"
        )
    except smtplib.SMTPRecipientsRefused as e:
        raise EnvioFallido(f"Destinatario rechazado: {e.recipients}")
    except (smtplib.SMTPException, socket.error, OSError) as e:
        raise EnvioFallido(f"{type(e).__name__}: {e}")

    real = msg["To"]
    return f"enviado a {real}"
