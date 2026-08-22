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

# Vocabulario antiguo que puede aparecer en JSONs o filas heredadas.
# `estado` (Scraped/Enriched) describe el progreso del scraping, NO la etapa de venta.
_LEGACY_STAGES = {
    "scraped": "Nuevo",
    "enriched": "Nuevo",
    "new": "Nuevo",
    "contacted": "Contactado",
    "replied": "Respuesta",
    "closed": "Cerrado",
    "discarded": "Descartado",
}


def normalize_stage(value) -> str:
    """
    Devuelve siempre una etapa válida de PIPELINE_STAGES.

    Cualquier valor nulo, vacío, con otro uso de mayúsculas o desconocido
    cae en 'Nuevo'. Evita el ValueError de PIPELINE_STAGES.index() que
    tumbaría la app entera (ver BUG-2).
    """
    if value is None:
        return PIPELINE_STAGES[0]
    raw = str(value).strip()
    if not raw:
        return PIPELINE_STAGES[0]
    for stage in PIPELINE_STAGES:
        if raw.casefold() == stage.casefold():
            return stage
    return _LEGACY_STAGES.get(raw.casefold(), PIPELINE_STAGES[0])


def stage_index(value) -> int:
    """Índice seguro para un st.selectbox de etapas."""
    return PIPELINE_STAGES.index(normalize_stage(value))


def _is_cloud() -> bool:
    """Detecta si hay credenciales de Turso configuradas."""
    return bool(os.environ.get("TURSO_DATABASE_URL"))


def get_conn():
    """Abre conexión a Turso (cloud) o SQLite local (desarrollo)."""
    if _is_cloud():
        from src.crm.turso_http import TursoConnection
        conn = TursoConnection(
            os.environ["TURSO_DATABASE_URL"],
            os.environ.get("TURSO_AUTH_TOKEN", ""),
        )
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")

    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea las tablas necesarias si no existen."""
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
            perfil_origen  TEXT DEFAULT '',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scrap_profiles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre          TEXT NOT NULL,
            search_query    TEXT DEFAULT 'Clínica de psicología en {city}',
            ciudades        TEXT DEFAULT '[]',
            min_reviews     INTEGER DEFAULT 20,
            min_rating      REAL DEFAULT 4.0,
            require_website TEXT DEFAULT 'required',
            max_scrolls     INTEGER DEFAULT 20,
            auto_import     INTEGER DEFAULT 1,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migraciones: añadir columnas a tablas ya existentes
    for stmt in [
        "ALTER TABLE leads ADD COLUMN perfil_origen TEXT DEFAULT ''",
        "ALTER TABLE scrap_profiles ADD COLUMN auto_import INTEGER DEFAULT 1",
    ]:
        try:
            conn.execute(stmt)
        except Exception:
            pass  # columna ya existe
    repair_invalid_stages(conn)
    conn.commit()
    conn.close()


def repair_invalid_stages(conn=None) -> int:
    """
    Corrige filas cuya `etapa` no pertenece a PIPELINE_STAGES.

    Cubre valores nulos, vacíos, heredados o escritos a mano en la consola
    de Turso. Es idempotente: si no hay nada que arreglar, no escribe.
    Retorna el número de filas corregidas.
    """
    own_conn = conn is None
    conn = conn or get_conn()
    placeholders = ",".join("?" * len(PIPELINE_STAGES))
    try:
        rows = conn.execute(
            f"SELECT id, etapa FROM leads "
            f"WHERE etapa IS NULL OR etapa NOT IN ({placeholders})",
            tuple(PIPELINE_STAGES),
        ).fetchall()
    except Exception:
        # La tabla puede no existir todavía en el primer arranque
        if own_conn:
            conn.close()
        return 0

    if rows:
        conn.executemany(
            "UPDATE leads SET etapa = ? WHERE id = ?",
            [(normalize_stage(r["etapa"]), r["id"]) for r in rows],
        )
        conn.commit()

    if own_conn:
        conn.close()
    return len(rows)


def import_leads(leads: list[dict], perfil_origen: str = "") -> int:
    """
    Importa una lista de leads (dicts).
    Salta duplicados (mismo nombre + ciudad).
    Retorna el número de leads importados.
    """
    conn = get_conn()
    init_db()

    existing = conn.execute("SELECT nombre, ciudad FROM leads").fetchall()
    existing_keys = {(r["nombre"], r["ciudad"]) for r in existing}

    new_leads = [
        l for l in leads
        if (l["nombre"], l["ciudad"]) not in existing_keys
    ]

    if not new_leads:
        conn.close()
        return 0

    sql = """
        INSERT INTO leads (nombre, ciudad, direccion, telefono, url,
                         puntuacion, resenas, director, email_directo,
                         email_generico, sociedad, etapa, perfil_origen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    params_list = [
        (
            l.get("nombre", ""),
            l.get("ciudad", ""),
            l.get("direccion", "").strip(),
            l.get("telefono", "").strip(),
            l.get("url", ""),
            l.get("puntuacion", 0),
            l.get("resenas", 0),
            l.get("director", ""),
            l.get("email_directo", ""),
            l.get("email_generico", ""),
            l.get("sociedad", ""),
            normalize_stage(l.get("etapa")),
            perfil_origen,
        )
        for l in new_leads
    ]

    conn.executemany(sql, params_list)
    conn.commit()
    conn.close()
    return len(new_leads)


def import_from_json(json_path: str | Path, perfil_origen: str = "") -> int:
    """Importa leads desde un fichero JSON."""
    json_path = Path(json_path)
    with open(json_path, "r", encoding="utf-8") as f:
        leads = json.load(f)
    return import_leads(leads, perfil_origen=perfil_origen)


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


def clear_all_leads() -> int:
    """Borra todos los leads. Retorna el número de filas eliminadas."""
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    conn.execute("DELETE FROM leads")
    conn.commit()
    conn.close()
    return count


def get_leads_to_enrich(limit: int | None = None) -> list[dict]:
    """
    Leads con web pero sin ningún dato de enriquecimiento.

    Se usa cuando el enricher corre en cloud sin `leads_raw.json` en disco
    (modo 'enricher' suelto en GitHub Actions, que arranca de checkout limpio).
    """
    conn = get_conn()
    sql = """
        SELECT id, nombre, ciudad, direccion, telefono, url,
               puntuacion, resenas, director, email_directo,
               email_generico, sociedad
          FROM leads
         WHERE url != ''
           AND director = ''
           AND email_directo = ''
           AND email_generico = ''
         ORDER BY puntuacion DESC, resenas DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_lead_enrichment(
    lead_id: int,
    director: str,
    email_directo: str,
    email_generico: str,
    sociedad: str,
):
    """Guarda el resultado del enriquecimiento de un lead."""
    conn = get_conn()
    conn.execute(
        """
        UPDATE leads
           SET director = ?, email_directo = ?, email_generico = ?,
               sociedad = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
        """,
        (director, email_directo, email_generico, sociedad, lead_id),
    )
    conn.commit()
    conn.close()


def update_lead_stage(lead_id: int, new_stage: str):
    """Mueve un lead a otra etapa del pipeline."""
    conn = get_conn()
    conn.execute(
        "UPDATE leads SET etapa = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (normalize_stage(new_stage), lead_id),
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


# ======================================================
# SCRAP PROFILES
# ======================================================

def save_scrap_profile(
    nombre: str,
    search_query: str,
    ciudades: list,
    min_reviews: int,
    min_rating: float,
    require_website: str,
    max_scrolls: int,
    auto_import: bool = True,
) -> int:
    """Guarda un perfil de scraping. Retorna el id creado."""
    conn = get_conn()
    conn.execute("""
        INSERT INTO scrap_profiles
            (nombre, search_query, ciudades, min_reviews, min_rating,
             require_website, max_scrolls, auto_import)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (nombre, search_query, json.dumps(ciudades, ensure_ascii=False),
          min_reviews, min_rating, require_website, max_scrolls, int(auto_import)))
    conn.commit()
    row = conn.execute("SELECT id FROM scrap_profiles ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row[0] if row else -1


def get_scrap_profiles() -> list[dict]:
    """Retorna todos los perfiles guardados."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM scrap_profiles ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    profiles = []
    for r in rows:
        p = dict(r)
        p["ciudades"] = json.loads(p["ciudades"]) if p["ciudades"] else []
        profiles.append(p)
    return profiles


def get_scrap_profile(profile_id: int) -> dict | None:
    """Retorna un perfil por id."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM scrap_profiles WHERE id = ?", (profile_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    p = dict(row)
    p["ciudades"] = json.loads(p["ciudades"]) if p["ciudades"] else []
    return p


def update_scrap_profile(
    profile_id: int,
    nombre: str,
    search_query: str,
    ciudades: list,
    min_reviews: int,
    min_rating: float,
    require_website: str,
    max_scrolls: int,
    auto_import: bool = True,
):
    """Actualiza un perfil existente."""
    conn = get_conn()
    conn.execute("""
        UPDATE scrap_profiles
        SET nombre=?, search_query=?, ciudades=?, min_reviews=?,
            min_rating=?, require_website=?, max_scrolls=?, auto_import=?
        WHERE id=?
    """, (nombre, search_query, json.dumps(ciudades, ensure_ascii=False),
          min_reviews, min_rating, require_website, max_scrolls,
          int(auto_import), profile_id))
    conn.commit()
    conn.close()


def delete_scrap_profile(profile_id: int):
    """Elimina un perfil."""
    conn = get_conn()
    conn.execute("DELETE FROM scrap_profiles WHERE id = ?", (profile_id,))
    conn.commit()
    conn.close()

