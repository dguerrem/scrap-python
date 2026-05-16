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
    estado: str = "Scraped"

    def to_dict(self) -> dict:
        """Convierte el lead a diccionario (para JSON/CSV)."""
        return asdict(self)

    @property
    def dedup_key(self) -> str:
        """Clave única para detectar duplicados (nombre + dirección)."""
        return f"{self.nombre.lower().strip()}|{self.direccion.lower().strip()}"
