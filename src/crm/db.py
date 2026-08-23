"""
Fase 3 — Base de datos para el CRM.
Soporta SQLite local (desarrollo) y Turso cloud (producción).
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from src.models.lead import clean_text, make_dedup_key

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_links (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT DEFAULT 'General',
            titulo    TEXT NOT NULL,
            url       TEXT NOT NULL,
            para_que  TEXT DEFAULT '',
            orden     INTEGER DEFAULT 100
        )
    """)
    seed_app_links(conn)
    # Migraciones: añadir columnas a tablas ya existentes
    for stmt in [
        "ALTER TABLE leads ADD COLUMN perfil_origen TEXT DEFAULT ''",
        "ALTER TABLE scrap_profiles ADD COLUMN auto_import INTEGER DEFAULT 1",
        "ALTER TABLE leads ADD COLUMN dedup_key TEXT DEFAULT ''",
        # Índice parcial: las filas con clave vacía quedan fuera, para que una
        # inserción manual sin dedup_key no reviente. backfill_dedup_keys() se
        # la calculará en el siguiente arranque.
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_dedup_key "
        "ON leads(dedup_key) WHERE dedup_key != ''",
    ]:
        try:
            conn.execute(stmt)
        except Exception:
            pass  # columna ya existe
    repair_invalid_stages(conn)
    backfill_dedup_keys(conn)
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


def _lead_richness(row) -> tuple:
    """
    Puntúa cuánta información útil tiene una fila, para decidir cuál conservar
    al colapsar duplicados. Mayor es mejor; el id bajo desempata.
    """
    score = 0
    if (row["notas"] or "").strip():
        score += 8          # el trabajo manual es lo más caro de recuperar
    if normalize_stage(row["etapa"]) != PIPELINE_STAGES[0]:
        score += 4          # ya avanzó en el pipeline
    if (row["email_directo"] or "").strip():
        score += 2
    if (row["email_generico"] or "").strip():
        score += 1
    if (row["director"] or "").strip():
        score += 1
    return (score, -row["id"])


def backfill_dedup_keys(conn=None) -> dict:
    """
    Migra la columna `dedup_key`: calcula las claves que falten y colapsa las
    filas que resulten duplicadas bajo el nuevo criterio.

    Se hace en una sola pasada y **se borran los duplicados antes de escribir
    las claves**, porque el índice único rechazaría el segundo UPDATE de un
    par duplicado. De cada grupo sobrevive la fila con más información útil
    (ver `_lead_richness`).

    Idempotente y barata: si no hay ninguna clave pendiente, no lee la tabla
    entera ni escribe nada. Retorna un resumen del trabajo hecho.
    """
    own_conn = conn is None
    conn = conn or get_conn()
    resumen = {"claves": 0, "duplicados": 0}

    try:
        pendientes = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE dedup_key IS NULL OR dedup_key = ''"
        ).fetchone()[0]
    except Exception:
        # La tabla o la columna pueden no existir todavía en el primer arranque
        if own_conn:
            conn.close()
        return resumen

    if not pendientes:
        if own_conn:
            conn.close()
        return resumen

    filas = conn.execute(
        "SELECT id, nombre, ciudad, direccion, dedup_key, notas, etapa, "
        "       email_directo, email_generico, director "
        "  FROM leads ORDER BY id"
    ).fetchall()

    grupos = {}
    objetivo = {}
    for r in filas:
        key = r["dedup_key"] or make_dedup_key(r["nombre"], r["ciudad"], r["direccion"])
        objetivo[r["id"]] = key
        grupos.setdefault(key, []).append(r)

    borrar, actualizar = [], []
    for key, miembros in grupos.items():
        if len(miembros) > 1:
            mejor = max(miembros, key=_lead_richness)
            borrar += [r["id"] for r in miembros if r["id"] != mejor["id"]]
            miembros = [mejor]
        for r in miembros:
            if (r["dedup_key"] or "") != key:
                actualizar.append((key, r["id"]))

    if borrar:
        conn.executemany("DELETE FROM leads WHERE id = ?", [(i,) for i in borrar])
        conn.commit()
        resumen["duplicados"] = len(borrar)

    if actualizar:
        conn.executemany("UPDATE leads SET dedup_key = ? WHERE id = ?", actualizar)
        conn.commit()
        resumen["claves"] = len(actualizar)

    if own_conn:
        conn.close()
    return resumen


def import_leads(leads: list[dict], perfil_origen: str = "") -> int:
    """
    Importa una lista de leads (dicts).

    Salta los que ya existan según `make_dedup_key()` (nombre + dirección, o
    nombre + ciudad si no hay dirección) y también los repetidos dentro del
    propio lote. Retorna el número de leads realmente insertados.
    """
    init_db()
    conn = get_conn()

    existing_keys = {
        r["dedup_key"]
        for r in conn.execute("SELECT dedup_key FROM leads").fetchall()
    }

    new_leads = []
    for l in leads:
        nombre = clean_text(l.get("nombre", ""))
        if not nombre:
            continue  # sin nombre no hay lead
        key = make_dedup_key(nombre, l.get("ciudad", ""), l.get("direccion", ""))
        if key in existing_keys:
            continue
        existing_keys.add(key)  # evita duplicados dentro del mismo lote
        new_leads.append((l, nombre, key))

    if not new_leads:
        conn.close()
        return 0

    sql = """
        INSERT OR IGNORE INTO leads (nombre, ciudad, direccion, telefono, url,
                         puntuacion, resenas, director, email_directo,
                         email_generico, sociedad, etapa, perfil_origen, dedup_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    params_list = [
        (
            nombre,
            clean_text(l.get("ciudad", "")),
            clean_text(l.get("direccion", "")),
            clean_text(l.get("telefono", "")),
            l.get("url", ""),
            l.get("puntuacion", 0),
            l.get("resenas", 0),
            clean_text(l.get("director", "")),
            l.get("email_directo", ""),
            l.get("email_generico", ""),
            clean_text(l.get("sociedad", "")),
            normalize_stage(l.get("etapa")),
            # El perfil del lote manda; si no se pasa, se respeta el que traiga
            # el propio lead (restauración de backups, JSON ya etiquetado).
            perfil_origen or l.get("perfil_origen", "") or "",
            key,
        )
        for l, nombre, key in new_leads
    ]

    antes = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    conn.executemany(sql, params_list)
    conn.commit()
    despues = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    conn.close()
    return despues - antes


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


# ======================================================
# ENLACES IMPORTANTES (tab Guía)
# ======================================================

# Se siembran una sola vez. A partir de ahí se editan desde la UI, para poder
# añadir recursos sin tocar código. La URL de Turso y la del repo dependen de
# la cuenta, así que se dejan vacías para que el usuario las complete.
_LINKS_SEED = [
    ("Operación", "Panel de Turso", "https://turso.tech/app",
     "Ver y editar la base de datos cloud, sacar credenciales", 10),
    ("Operación", "GitHub Actions del repo", "https://github.com/dguerrem/scrap-python/actions",
     "Ver ejecuciones del scraper, logs y estado", 20),
    ("Operación", "Streamlit Cloud", "https://share.streamlit.io/",
     "Gestionar la app: reiniciar, ver logs, dormir/despertar", 30),
    ("Configuración", "Secrets de GitHub", "https://github.com/dguerrem/scrap-python/settings/secrets/actions",
     "TURSO_DATABASE_URL, TURSO_AUTH_TOKEN y los del mailer", 40),
    ("Configuración", "Sharing de Streamlit", "https://share.streamlit.io/",
     "Restringir quién puede ver el CRM (App settings → Sharing)", 50),
    ("Google", "Admin de Google Workspace", "https://admin.google.com/",
     "Gestión del correo, DKIM, dominios", 60),
    ("Google", "Contraseñas de aplicación", "https://myaccount.google.com/apppasswords",
     "Generar o revocar la credencial SMTP del mailer", 70),
    ("Google", "Seguridad de la cuenta", "https://myaccount.google.com/security",
     "Activar la verificación en 2 pasos (requisito del App Password)", 80),
    ("Negocio", "Web de PsycoERP", "https://psycoerp.es",
     "La landing del producto", 90),
]


def seed_app_links(conn=None) -> int:
    """Siembra los enlaces por defecto la primera vez. Idempotente."""
    own_conn = conn is None
    conn = conn or get_conn()
    try:
        existe = conn.execute("SELECT COUNT(*) FROM app_links").fetchone()[0]
    except Exception:
        if own_conn:
            conn.close()
        return 0
    if existe:
        if own_conn:
            conn.close()
        return 0
    conn.executemany(
        "INSERT INTO app_links (categoria, titulo, url, para_que, orden) "
        "VALUES (?, ?, ?, ?, ?)",
        _LINKS_SEED,
    )
    conn.commit()
    if own_conn:
        conn.close()
    return len(_LINKS_SEED)


def get_app_links() -> list:
    """Todos los enlaces, ordenados por categoría."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM app_links ORDER BY orden, categoria, titulo"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_app_link(categoria: str, titulo: str, url: str, para_que: str = "",
                  orden: int = 100) -> int:
    conn = get_conn()
    conn.execute(
        "INSERT INTO app_links (categoria, titulo, url, para_que, orden) "
        "VALUES (?, ?, ?, ?, ?)",
        (categoria.strip() or "General", titulo.strip(), url.strip(),
         para_que.strip(), int(orden)),
    )
    conn.commit()
    conn.close()
    return 1


def update_app_link(link_id: int, categoria: str, titulo: str, url: str,
                    para_que: str = "", orden: int = 100):
    conn = get_conn()
    conn.execute(
        "UPDATE app_links SET categoria = ?, titulo = ?, url = ?, "
        "para_que = ?, orden = ? WHERE id = ?",
        (categoria.strip() or "General", titulo.strip(), url.strip(),
         para_que.strip(), int(orden), link_id),
    )
    conn.commit()
    conn.close()


def delete_app_link(link_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM app_links WHERE id = ?", (link_id,))
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

