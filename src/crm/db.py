"""
Fase 3 — Base de datos para el CRM.
Soporta SQLite local (desarrollo) y Turso cloud (producción).
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "crm.db"

# Estados del pipeline de ventas (columnas del Kanban)
PIPELINE_STAGES = [
    "Nuevo",        # Recién importado, sin contactar
    "Contactado",   # Email enviado
    "Respuesta",    # Han respondido (positiva o negativa)
    "Demo",         # Demo agendada o realizada
    "Cerrado",      # Venta cerrada (ganada o perdida)
    "Descartado",   # No cualificado / no interesado
]


def _is_cloud() -> bool:
    """Detecta si hay credenciales de Turso configuradas."""
    return bool(os.environ.get("TURSO_DATABASE_URL"))


def get_conn():
    """Abre conexión a Turso (cloud) o SQLite local (desarrollo)."""
    if _is_cloud():
        import libsql_experimental as libsql
        conn = libsql.connect(
            os.environ["TURSO_DATABASE_URL"],
            auth_token=os.environ.get("TURSO_AUTH_TOKEN", ""),
        )
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")

    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea la tabla de leads si no existe."""
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre      TEXT NOT NULL,
            ciudad      TEXT NOT NULL DEFAULT '',
            direccion   TEXT DEFAULT '',
            telefono    TEXT DEFAULT '',
            url         TEXT DEFAULT '',
            puntuacion  REAL DEFAULT 0.0,
            resenas     INTEGER DEFAULT 0,
            director    TEXT DEFAULT '',
            email_directo  TEXT DEFAULT '',
            email_generico TEXT DEFAULT '',
            sociedad    TEXT DEFAULT '',
            etapa       TEXT DEFAULT 'Nuevo',
            notas       TEXT DEFAULT '',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def import_leads(leads: list[dict]) -> int:
    """
    Importa una lista de leads (dicts).
    Salta duplicados (mismo nombre + ciudad).
    Retorna el número de leads importados.
    """
    conn = get_conn()
    init_db()
    imported = 0

    for lead in leads:
        existing = conn.execute(
            "SELECT id FROM leads WHERE nombre = ? AND ciudad = ?",
            (lead["nombre"], lead["ciudad"]),
        ).fetchone()

        if existing:
            continue

        conn.execute("""
            INSERT INTO leads (nombre, ciudad, direccion, telefono, url,
                             puntuacion, resenas, director, email_directo,
                             email_generico, sociedad, etapa)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            lead.get("nombre", ""),
            lead.get("ciudad", ""),
            lead.get("direccion", "").strip(),
            lead.get("telefono", "").strip(),
            lead.get("url", ""),
            lead.get("puntuacion", 0),
            lead.get("resenas", 0),
            lead.get("director", ""),
            lead.get("email_directo", ""),
            lead.get("email_generico", ""),
            lead.get("sociedad", ""),
            "Nuevo",
        ))
        imported += 1

    conn.commit()
    conn.close()
    return imported


def import_from_json(json_path: str | Path) -> int:
    """Importa leads desde un fichero JSON."""
    json_path = Path(json_path)
    with open(json_path, "r", encoding="utf-8") as f:
        leads = json.load(f)
    return import_leads(leads)


def get_leads_by_stage(etapa: str) -> list:
    """Obtiene todos los leads de una etapa del pipeline."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM leads WHERE etapa = ? ORDER BY puntuacion DESC, resenas DESC",
        (etapa,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_leads() -> list:
    """Obtiene todos los leads."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM leads ORDER BY etapa, puntuacion DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_lead_stage(lead_id: int, new_stage: str):
    """Mueve un lead a otra etapa del pipeline."""
    conn = get_conn()
    conn.execute(
        "UPDATE leads SET etapa = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_stage, lead_id),
    )
    conn.commit()
    conn.close()


def update_lead_notes(lead_id: int, notas: str):
    """Actualiza las notas de un lead."""
    conn = get_conn()
    conn.execute(
        "UPDATE leads SET notas = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (notas, lead_id),
    )
    conn.commit()
    conn.close()


def get_stats() -> dict:
    """Estadísticas del pipeline."""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    with_email = conn.execute(
        "SELECT COUNT(*) FROM leads WHERE email_directo != '' OR email_generico != ''"
    ).fetchone()[0]
    with_director = conn.execute(
        "SELECT COUNT(*) FROM leads WHERE director != ''"
    ).fetchone()[0]

    by_stage = {}
    for stage in PIPELINE_STAGES:
        count = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE etapa = ?", (stage,)
        ).fetchone()[0]
        by_stage[stage] = count

    conn.close()
    return {
        "total": total,
        "con_email": with_email,
        "con_director": with_director,
        "por_etapa": by_stage,
    }
