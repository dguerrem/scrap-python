"""
Configuración del mailer: credenciales SMTP y modos de prueba.

Las credenciales **nunca** viven en la BD ni en el repositorio (que es
público). Se leen de variables de entorno y, si no están, de
`.streamlit/secrets.toml` — que está en `.gitignore` — para no obligar a
exportar cinco variables cada vez que se prueba en local.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECRETS_FILE = ROOT / ".streamlit" / "secrets.toml"
OUTBOX_DIR = ROOT / "data" / "emails_out"

_CLAVES = (
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_APP_PASSWORD",
    "EMAIL_FROM_NAME", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN",
)

_DEFAULTS = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "EMAIL_FROM_NAME": "Info | PsycoERP",
}

_cache: dict | None = None


def _leer_secrets() -> dict:
    """Lector mínimo de `clave = "valor"`. Evita depender de tomllib (3.11+)."""
    if not SECRETS_FILE.exists():
        return {}
    valores = {}
    patron = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"(.*)"\s*$')
    for linea in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
        if linea.lstrip().startswith("#"):
            continue
        m = patron.match(linea)
        if m:
            valores[m.group(1)] = m.group(2)
    return valores


def get(clave: str, default: str = "") -> str:
    """Valor de configuración: entorno > secrets.toml > default."""
    global _cache
    if os.environ.get(clave):
        return os.environ[clave]
    if _cache is None:
        _cache = _leer_secrets()
    return _cache.get(clave) or _DEFAULTS.get(clave, default)


def reload():
    """Olvida el fichero cacheado (para tests)."""
    global _cache
    _cache = None


def smtp_config() -> dict:
    return {
        "host": get("SMTP_HOST"),
        "port": int(get("SMTP_PORT", "587") or "587"),
        "user": get("SMTP_USER"),
        "password": get("SMTP_APP_PASSWORD"),
        "from_name": get("EMAIL_FROM_NAME") or get("SMTP_FROM_NAME"),
        "reply_to": get("EMAIL_REPLY_TO") or get("SMTP_REPLY_TO"),
    }


def smtp_listo() -> tuple[bool, str]:
    """¿Hay credenciales suficientes para enviar de verdad?"""
    cfg = smtp_config()
    if not cfg["user"]:
        return False, "Falta SMTP_USER"
    if not cfg["password"]:
        return False, "Falta SMTP_APP_PASSWORD"
    return True, ""


# ======================================================
# MODOS DE PRUEBA (6.6 del README)
# ======================================================

def _flag(nombre: str) -> bool:
    return os.environ.get(nombre, "").strip() not in ("", "0", "false", "False")


def dry_run() -> bool:
    """No envía nada: escribe cada mensaje en data/emails_out/*.eml."""
    return _flag("EMAIL_DRY_RUN")


def redirect_to() -> str:
    """Envía de verdad, pero todo a esta dirección."""
    return os.environ.get("EMAIL_REDIRECT_TO", "").strip()


def fast_clock() -> bool:
    """Intervalos en segundos en lugar de minutos, y sin ventana horaria."""
    return _flag("EMAIL_FAST_CLOCK")


def force_window() -> bool:
    """Ignora sólo la restricción L-V 08:00-15:00."""
    return _flag("EMAIL_FORCE_WINDOW")


def modo_prueba_activo() -> list[str]:
    """Lista legible de los modos de prueba activos, para avisar en la UI."""
    activos = []
    if dry_run():
        activos.append("DRY_RUN (no se envía nada)")
    if redirect_to():
        activos.append(f"REDIRECT_TO ({redirect_to()})")
    if fast_clock():
        activos.append("FAST_CLOCK (segundos en vez de minutos)")
    if force_window():
        activos.append("FORCE_WINDOW (sin horario)")
    return activos
