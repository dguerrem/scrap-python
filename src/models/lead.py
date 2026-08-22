"""Modelo de datos para un lead (clínica de psicología)."""

from __future__ import annotations

from dataclasses import dataclass, asdict


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
        """Clave única para detectar duplicados (nombre + dirección)."""
        return f"{self.nombre.lower().strip()}|{self.direccion.lower().strip()}"
