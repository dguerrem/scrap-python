"""
CRM de PsycoLead — panel de ventas de PsycoERP.

Este fichero sólo monta la página: configuración, barra lateral y tabs.
Cada tab vive en src/crm/views/.

Ejecutar: streamlit run src/crm/app.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st

# ── Turso: propagar secrets a env vars antes de importar db ──
try:
    if "TURSO_DATABASE_URL" in st.secrets:
        os.environ["TURSO_DATABASE_URL"] = st.secrets["TURSO_DATABASE_URL"]
        os.environ["TURSO_AUTH_TOKEN"] = st.secrets["TURSO_AUTH_TOKEN"]
    for _k in ("GITHUB_PAT", "GITHUB_REPO"):
        if _k in st.secrets:
            os.environ[_k] = st.secrets[_k]
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.crm.db import init_db, import_from_json, import_leads, clear_all_leads
from src.crm.views import _components as ui
from src.crm.views import guia, kanban, tabla, detalle, scrap

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

st.set_page_config(
    page_title="PsycoLead CRM",
    page_icon="🧠",
    layout="wide",
)

init_db()


# ======================================================
# BARRA LATERAL
# ======================================================

def _sidebar_importar():
    """Entradas de datos manuales. Rara vez se usan: van plegadas."""
    json_enriched = DATA_DIR / "leads_enriched.json"
    json_raw = DATA_DIR / "leads_raw.json"

    def _importar(path):
        count = import_from_json(path)
        if count:
            st.success(f"✅ {count} leads importados")
            ui.clear_cache()
            st.rerun()
        else:
            st.info("No hay leads nuevos")

    if json_enriched.exists():
        if st.button("Importar leads con email", type="primary",
                     use_container_width=True):
            _importar(json_enriched)

    if json_raw.exists():
        if st.button("Importar leads sin enriquecer", use_container_width=True):
            _importar(json_raw)

    uploaded = st.file_uploader("Subir un JSON de leads", type=["json"])
    if uploaded:
        count = import_leads(json.load(uploaded))
        if count:
            st.success(f"✅ {count} leads importados")
            ui.clear_cache()
            st.rerun()
        else:
            st.info("No hay leads nuevos")


def _sidebar_peligro():
    st.caption("Esto borra leads. No hay deshacer.")
    confirm = st.checkbox("Sé lo que hago")
    if st.button("🗑️ Vaciar todos los leads", disabled=not confirm,
                 use_container_width=True):
        deleted = clear_all_leads()
        st.success(f"✅ {deleted} leads eliminados")
        ui.clear_cache()
        st.rerun()


with st.sidebar:
    st.title("🧠 PsycoLead CRM")

    _stats = ui.c_get_stats()
    _m1, _m2 = st.columns(2)
    _m1.metric("Leads", _stats["total"])
    _m2.metric("Con email", _stats["con_email"])

    st.divider()

    st.markdown("**🔎 Filtros**")
    _all_leads = ui.c_get_all_leads()
    criterios = ui.render_filters(_all_leads)

    st.divider()

    with st.expander("📥 Importar datos"):
        _sidebar_importar()

    with st.expander("⚠️ Zona peligrosa"):
        _sidebar_peligro()

    st.caption("PsycoERP · 2.500 € pago único")


# ======================================================
# TABS
# ======================================================

tab_guia, tab_kanban, tab_tabla, tab_detalle, tab_scrap = st.tabs(
    ["📖 Guía", "📋 Kanban", "📊 Tabla", "🔍 Detalle", "⚙️ Scrap"]
)

with tab_guia:
    guia.render()

with tab_kanban:
    kanban.render(criterios)

with tab_tabla:
    tabla.render(criterios)

with tab_detalle:
    detalle.render(criterios)

with tab_scrap:
    scrap.render()
