"""
Saneado de datos personales en los logs.

El repositorio es **público**, y con él los logs de GitHub Actions: cualquiera
puede leer la salida de un run sin estar autenticado. Sin este módulo, cada
ejecución publicaba un listado de clínicas con el nombre de su director y su
email — exactamente la base de datos que estamos construyendo, servida gratis.

En local no se oculta nada: ahí los logs son la herramienta de depuración.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re

# GitHub Actions define ambas. CI es el estándar de facto del resto de runners.
IN_CI = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def mask(value) -> str:
    """
    Identificador estable de un dato personal.

    En local devuelve el valor tal cual. En CI devuelve un hash corto, que
    permite seguir distinguiendo y correlacionando líneas del log (dos '<a1b2c3>'
    son la misma clínica) sin revelar de quién se trata.
    """
    text = str(value or "").strip()
    if not IN_CI or not text:
        return text
    return f"<{hashlib.sha1(text.encode('utf-8')).hexdigest()[:6]}>"


def show(value, si: str = "sí", no: str = "no") -> str:
    """
    Valor sensible del que en CI sólo interesa saber si existe.

    En local devuelve el contenido; en CI, únicamente 'sí' o 'no'. Se usa para
    emails y nombres de director, donde el dato en sí no aporta nada al
    diagnóstico de un run pero sí lo aporta su presencia.
    """
    if not IN_CI:
        return str(value) if value else no
    return si if value else no


class RedactEmailsFilter(logging.Filter):
    """
    Red de seguridad: borra cualquier email del mensaje ya formateado.

    `mask()` y `show()` cubren las líneas conocidas, pero un mensaje de error de
    una librería de terceros puede arrastrar un email en el texto de la
    excepción. Este filtro actúa sobre el resultado final, venga de donde venga.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not IN_CI:
            return True
        try:
            mensaje = record.getMessage()
        except Exception:
            return True
        if "@" in mensaje:
            limpio = _EMAIL_RE.sub("<email>", mensaje)
            if limpio != mensaje:
                record.msg = limpio
                record.args = ()
        return True


def install_log_redaction() -> None:
    """Instala el filtro en el logger raíz. Idempotente."""
    root = logging.getLogger()
    for h in root.handlers:
        if not any(isinstance(f, RedactEmailsFilter) for f in h.filters):
            h.addFilter(RedactEmailsFilter())
    if not any(isinstance(f, RedactEmailsFilter) for f in root.filters):
        root.addFilter(RedactEmailsFilter())
