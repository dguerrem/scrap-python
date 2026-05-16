"""
Fase 3 — CRM Kanban con Streamlit.
Panel visual para gestionar el pipeline de ventas de PsycoERP.

Ejecutar: streamlit run src/crm/app.py
"""

from __future__ import annotations

import json
import os
import streamlit as st
from pathlib import Path

# ── Turso: propagar secrets a env vars antes de importar db ──
try:
    if "TURSO_DATABASE_URL" in st.secrets:
        os.environ["TURSO_DATABASE_URL"] = st.secrets["TURSO_DATABASE_URL"]
        os.environ["TURSO_AUTH_TOKEN"] = st.secrets["TURSO_AUTH_TOKEN"]
except Exception:
    pass

# Importar módulo de base de datos
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.crm.db import (
    init_db, import_from_json, import_leads, get_leads_by_stage, get_all_leads,
    update_lead_stage, update_lead_notes, get_stats, PIPELINE_STAGES,
)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# ======================================================
# CONFIGURACIÓN DE PÁGINA
# ======================================================

st.set_page_config(
    page_title="PsycoLead CRM",
    page_icon="🧠",
    layout="wide",
)

# Inicializar DB
init_db()

# ======================================================
# SIDEBAR — Importar datos y estadísticas
# ======================================================

with st.sidebar:
    st.title("🧠 PsycoLead CRM")
    st.caption("Pipeline de ventas — PsycoERP")

    st.divider()

    # Botón para importar leads
    st.subheader("📥 Importar Leads")

    json_enriched = DATA_DIR / "leads_enriched.json"
    json_raw = DATA_DIR / "leads_raw.json"

    if json_enriched.exists():
        if st.button("Importar leads enriquecidos", type="primary", use_container_width=True):
            count = import_from_json(json_enriched)
            if count > 0:
                st.success(f"✅ {count} leads importados")
                st.rerun()
            else:
                st.info("No hay leads nuevos para importar")

    if json_raw.exists():
        if st.button("Importar leads crudos", use_container_width=True):
            count = import_from_json(json_raw)
            if count > 0:
                st.success(f"✅ {count} leads importados")
                st.rerun()
            else:
                st.info("No hay leads nuevos para importar")

    # ── Subir JSON (para deploy en la nube) ──
    uploaded = st.file_uploader("Subir JSON de leads", type=["json"])
    if uploaded:
        leads_data = json.load(uploaded)
        count = import_leads(leads_data)
        if count > 0:
            st.success(f"✅ {count} leads importados")
            st.rerun()
        else:
            st.info("No hay leads nuevos para importar")

    st.divider()

    # Estadísticas
    st.subheader("📊 Estadísticas")
    stats = get_stats()

    col1, col2 = st.columns(2)
    col1.metric("Total leads", stats["total"])
    col2.metric("Con email", stats["con_email"])

    col3, col4 = st.columns(2)
    col3.metric("Con director", stats["con_director"])
    col4.metric("Contactados", stats["por_etapa"].get("Contactado", 0))

    st.divider()
    st.caption("PsycoERP · €2.500 pago único")


# ======================================================
# VISTA PRINCIPAL — Tabs
# ======================================================

tab_kanban, tab_tabla, tab_detalle = st.tabs(["📋 Kanban", "📊 Tabla", "🔍 Detalle"])

# ======================================================
# TAB 1 — KANBAN
# ======================================================

with tab_kanban:
    cols = st.columns(len(PIPELINE_STAGES))

    for i, stage in enumerate(PIPELINE_STAGES):
        with cols[i]:
            leads = get_leads_by_stage(stage)
            st.subheader(f"{stage} ({len(leads)})")

            for lead in leads:
                # Determinar color del borde según datos disponibles
                has_direct = bool(lead["email_directo"])
                has_generic = bool(lead["email_generico"])
                has_director = bool(lead["director"])

                # Icono de calidad del lead
                if has_direct and has_director:
                    quality = "🟢"  # Mejor: email directo + nombre
                elif has_direct or has_director:
                    quality = "🟡"  # Bueno: tiene algo personal
                elif has_generic:
                    quality = "🟠"  # Aceptable: solo email genérico
                else:
                    quality = "🔴"  # Sin datos de contacto

                with st.expander(f"{quality} {lead['nombre'][:30]}"):
                    st.caption(f"📍 {lead['ciudad']} · ⭐ {lead['puntuacion']} · 💬 {lead['resenas']}")

                    if lead["director"]:
                        st.write(f"👤 **{lead['director']}**")
                    if lead["email_directo"]:
                        st.write(f"📧 {lead['email_directo']}")
                    elif lead["email_generico"]:
                        st.write(f"📧 {lead['email_generico']} *(genérico)*")
                    if lead["telefono"]:
                        st.write(f"📞 {lead['telefono']}")
                    if lead["sociedad"]:
                        st.caption(f"🏢 {lead['sociedad']}")

                    # Selector para mover de etapa
                    new_stage = st.selectbox(
                        "Mover a",
                        PIPELINE_STAGES,
                        index=PIPELINE_STAGES.index(stage),
                        key=f"stage_{lead['id']}",
                    )
                    if new_stage != stage:
                        update_lead_stage(lead["id"], new_stage)
                        st.rerun()

                    # Notas
                    notas = st.text_area(
                        "Notas",
                        value=lead["notas"] or "",
                        key=f"notas_{lead['id']}",
                        height=68,
                    )
                    if notas != (lead["notas"] or ""):
                        update_lead_notes(lead["id"], notas)


# ======================================================
# TAB 2 — TABLA COMPLETA
# ======================================================

with tab_tabla:
    all_leads = get_all_leads()

    if not all_leads:
        st.info("No hay leads. Importa datos desde la barra lateral.")
    else:
        # Filtros
        col_filter1, col_filter2, col_filter3 = st.columns(3)
        with col_filter1:
            filter_stage = st.multiselect(
                "Filtrar por etapa",
                PIPELINE_STAGES,
                default=PIPELINE_STAGES,
            )
        with col_filter2:
            filter_email = st.selectbox(
                "Filtrar por email",
                ["Todos", "Con email directo", "Con email genérico", "Sin email"],
            )
        with col_filter3:
            filter_city = st.multiselect(
                "Filtrar por ciudad",
                sorted(set(l["ciudad"] for l in all_leads)),
                default=sorted(set(l["ciudad"] for l in all_leads)),
            )

        # Aplicar filtros
        filtered = [l for l in all_leads if l["etapa"] in filter_stage and l["ciudad"] in filter_city]

        if filter_email == "Con email directo":
            filtered = [l for l in filtered if l["email_directo"]]
        elif filter_email == "Con email genérico":
            filtered = [l for l in filtered if l["email_generico"] and not l["email_directo"]]
        elif filter_email == "Sin email":
            filtered = [l for l in filtered if not l["email_directo"] and not l["email_generico"]]

        st.write(f"**{len(filtered)} leads**")

        # Tabla
        display_data = []
        for l in filtered:
            email = l["email_directo"] or l["email_generico"] or "—"
            display_data.append({
                "Nombre": l["nombre"],
                "Ciudad": l["ciudad"],
                "⭐": l["puntuacion"],
                "💬": l["resenas"],
                "Director": l["director"] or "—",
                "Email": email,
                "Sociedad": l["sociedad"] or "—",
                "Etapa": l["etapa"],
            })

        st.dataframe(display_data, use_container_width=True, hide_index=True)


# ======================================================
# TAB 3 — DETALLE DE LEAD
# ======================================================

with tab_detalle:
    all_leads = get_all_leads()

    if not all_leads:
        st.info("No hay leads. Importa datos desde la barra lateral.")
    else:
        lead_names = [f"{l['nombre']} ({l['ciudad']})" for l in all_leads]
        selected = st.selectbox("Seleccionar lead", lead_names)

        if selected:
            idx = lead_names.index(selected)
            lead = all_leads[idx]

            col1, col2 = st.columns([2, 1])

            with col1:
                st.subheader(lead["nombre"])
                st.write(f"📍 **Ciudad:** {lead['ciudad']}")
                st.write(f"📫 **Dirección:** {lead['direccion']}")
                st.write(f"📞 **Teléfono:** {lead['telefono']}")
                if lead["url"]:
                    st.write(f"🌐 **Web:** {lead['url']}")
                st.write(f"⭐ **Puntuación:** {lead['puntuacion']}  ·  💬 **Reseñas:** {lead['resenas']}")

                st.divider()
                st.write("**Datos de enriquecimiento:**")
                st.write(f"👤 **Director:** {lead['director'] or '—'}")
                st.write(f"📧 **Email directo:** {lead['email_directo'] or '—'}")
                st.write(f"📧 **Email genérico:** {lead['email_generico'] or '—'}")
                st.write(f"🏢 **Sociedad:** {lead['sociedad'] or '—'}")

            with col2:
                st.subheader("Pipeline")
                new_stage = st.selectbox(
                    "Etapa actual",
                    PIPELINE_STAGES,
                    index=PIPELINE_STAGES.index(lead["etapa"]),
                    key="detail_stage",
                )
                if new_stage != lead["etapa"]:
                    update_lead_stage(lead["id"], new_stage)
                    st.rerun()

                st.divider()
                notas = st.text_area(
                    "Notas",
                    value=lead["notas"] or "",
                    height=200,
                    key="detail_notas",
                )
                if notas != (lead["notas"] or ""):
                    update_lead_notes(lead["id"], notas)
                    st.success("Notas guardadas")
