"""Modelo de datos para un lead (clínica de psicología)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict

_WS = re.compile(r"\s+")

# Categorías Unicode a neutralizar: uso privado (Co), control (Cc) y formato (Cf).
# Google Maps antepone a la dirección un glifo de icono del área de uso privado
# (p. ej. '\ue0c8') seguido de un salto de línea. Si no se limpia, la misma
# clínica puede generar claves de deduplicación distintas entre ejecuciones.
_JUNK_CATEGORIES = ("Co", "Cc", "Cf")


def clean_text(value) -> str:
    """Limpia un texto para mostrarlo: quita glifos basura y espacios sobrantes."""
    if not value:
        return ""
    cleaned = "".join(
        " " if unicodedata.category(ch) in _JUNK_CATEGORIES else ch
        for ch in str(value)
    )
    return _WS.sub(" ", cleaned).strip()


def normalize_text(value) -> str:
    """Como clean_text(), pero además insensible a mayúsculas. Para claves."""
    return clean_text(value).casefold()


def make_dedup_key(nombre, ciudad="", direccion="") -> str:
    """
    Clave única de un lead, compartida por el scraper y la base de datos.

    Se usa `nombre + direccion`, que distingue correctamente las sedes de una
    misma cadena. Si la dirección viene vacía se recurre a `nombre + ciudad`,
    porque si no todos los leads sin dirección colapsarían en una sola clave.
    El prefijo '#' evita que una dirección que coincida con el nombre de una
    ciudad choque con esa variante.
    """
    n = normalize_text(nombre)
    d = normalize_text(direccion)
    return f"{n}|{d}" if d else f"{n}|#{normalize_text(ciudad)}"


@dataclass
class Lead:
    nombre: str
    ciudad: str
    direccion: str = ""
    telefono: str = ""
    url: str = ""
    puntuacion: float = 0.0
    resenas: int = 0
    estado: str = "Scraped"      # Progreso del scraping: Scraped | Enriched.
                                 # NO es la etapa de venta del CRM (`etapa` en BD).

    # Campos de enriquecimiento (Fase 2)
    director: str = ""           # Nombre del responsable/titular (Aviso Legal)
    email_directo: str = ""      # Email personal (nombre@, gerencia@, etc.)
    email_generico: str = ""     # Email genérico (info@, contacto@, etc.)
    sociedad: str = ""           # Razón social si aparece

    def to_dict(self) -> dict:
        """Convierte el lead a diccionario (para JSON/CSV)."""
        return asdict(self)

    @property
    def dedup_key(self) -> str:
        """Clave única para detectar duplicados. Ver make_dedup_key()."""
        return make_dedup_key(self.nombre, self.ciudad, self.direccion)
