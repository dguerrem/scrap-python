"""
Fase 3 — CRM Kanban con Streamlit.
Panel visual para gestionar el pipeline de ventas de PsycoERP.

Ejecutar: streamlit run src/crm/app.py
"""

from __future__ import annotations

import html as _html
import json
import os
import streamlit as st
from pathlib import Path

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

# Importar módulo de base de datos
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.crm.db import (
    init_db, import_from_json, import_leads, get_leads_by_stage, get_all_leads,
    update_lead_stage, update_lead_notes, get_stats, clear_all_leads,
    save_scrap_profile, get_scrap_profiles, get_scrap_profile,
    update_scrap_profile, delete_scrap_profile,
    PIPELINE_STAGES,
)
from src.crm import pipeline_runner

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


# ── Cache: evita llamadas repetidas a Turso en cada rerun ──
@st.cache_data(ttl=300)
def _c_get_all_leads():
    return [dict(r) for r in get_all_leads()]

@st.cache_data(ttl=300)
def _c_get_leads_by_stage(stage):
    return [dict(r) for r in get_leads_by_stage(stage)]

@st.cache_data(ttl=300)
def _c_get_stats():
    return get_stats()

@st.cache_data(ttl=300)
def _c_get_scrap_profiles():
    return get_scrap_profiles()


def _clear_cache():
    st.cache_data.clear()

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
                _clear_cache()
                st.rerun()
            else:
                st.info("No hay leads nuevos para importar")

    if json_raw.exists():
        if st.button("Importar leads crudos", use_container_width=True):
            count = import_from_json(json_raw)
            if count > 0:
                st.success(f"✅ {count} leads importados")
                _clear_cache()
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
            _clear_cache()
            st.rerun()
        else:
            st.info("No hay leads nuevos para importar")

    st.divider()

    # Estadísticas
    st.subheader("📊 Estadísticas")
    stats = _c_get_stats()

    col1, col2 = st.columns(2)
    col1.metric("Total leads", stats["total"])
    col2.metric("Con email", stats["con_email"])

    col3, col4 = st.columns(2)
    col3.metric("Con director", stats["con_director"])
    col4.metric("Contactados", stats["por_etapa"].get("Contactado", 0))

    st.divider()

    # ── Zona peligrosa ──
    st.subheader("⚠️ Gestión")
    confirm_clear = st.checkbox("Confirmar vaciado de leads")
    if st.button(
        "🗑️ Vaciar todos los leads",
        disabled=not confirm_clear,
        use_container_width=True,
    ):
        deleted = clear_all_leads()
        st.success(f"✅ {deleted} leads eliminados")
        _clear_cache()
        st.rerun()

    st.divider()
    st.caption("PsycoERP · €2.500 pago único")


# ======================================================
# VISTA PRINCIPAL — Tabs
# ======================================================

tab_kanban, tab_tabla, tab_detalle, tab_scrap = st.tabs(
    ["📋 Kanban", "📊 Tabla", "🔍 Detalle", "⚙️ Scrap"]
)

# ======================================================
# TAB 1 — KANBAN
# ======================================================

with tab_kanban:
    # Filtro por perfil de origen
    _all_leads_for_filter = _c_get_all_leads()
    _origenes = sorted({l.get("perfil_origen", "") or "(sin perfil)" for l in _all_leads_for_filter})
    if len(_origenes) > 1:
        _filtro_origen = st.multiselect(
            "Filtrar por perfil de origen",
            _origenes,
            default=_origenes,
            key="kanban_origen",
        )
    else:
        _filtro_origen = _origenes

    cols = st.columns(len(PIPELINE_STAGES))

    for i, stage in enumerate(PIPELINE_STAGES):
        with cols[i]:
            leads = [l for l in _c_get_leads_by_stage(stage)
                     if (l.get("perfil_origen") or "(sin perfil)") in _filtro_origen]
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
                    if lead.get("perfil_origen"):
                        st.caption(f"🎯 _{lead['perfil_origen']}_")

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
                        _clear_cache()
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
    all_leads = _c_get_all_leads()

    if not all_leads:
        st.info("No hay leads. Importa datos desde la barra lateral.")
    else:
        # Filtros
        col_filter1, col_filter2, col_filter3, col_filter4 = st.columns(4)
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
        with col_filter4:
            _tabla_origenes = sorted({l.get("perfil_origen", "") or "(sin perfil)" for l in all_leads})
            filter_origen = st.multiselect(
                "Filtrar por perfil origen",
                _tabla_origenes,
                default=_tabla_origenes,
            )

        # Aplicar filtros
        filtered = [l for l in all_leads
                    if l["etapa"] in filter_stage
                    and l["ciudad"] in filter_city
                    and (l.get("perfil_origen") or "(sin perfil)") in filter_origen]

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
                "Origen": l.get("perfil_origen") or "—",
            })

        st.dataframe(display_data, use_container_width=True, hide_index=True)


# ======================================================
# TAB 3 — DETALLE DE LEAD
# ======================================================

with tab_detalle:
    all_leads = _c_get_all_leads()

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
                if lead.get("perfil_origen"):
                    st.write(f"🎯 **Perfil origen:** {lead['perfil_origen']}")

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
                    _clear_cache()
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


# ======================================================
# TAB 4 — PERSONALIZADOR DE SCRAP
# ======================================================

_CITIES_OPTIONS = [
    "Madrid", "Barcelona", "Valencia", "Sevilla", "Málaga",
    "Bilbao", "Zaragoza", "Murcia", "Palma de Mallorca",
    "Las Palmas de Gran Canaria",
]

_WEB_OPTIONS = {
    "Solo con web (vender software)": "required",
    "Solo sin web (vender landing page)": "none",
    "Todos (sin filtro)": "any",
}
_WEB_LABELS = {v: k for k, v in _WEB_OPTIONS.items()}

_MODE_OPTIONS = {
    "🗺️ Solo Scraper (Google Maps)": "scraper",
    "🔍 Solo Enricher (emails + director)": "enricher",
    "🚀 Pipeline completa (scraper + enricher)": "pipeline",
}

with tab_scrap:
    st.subheader("⚙️ Perfiles de Búsqueda")

    # ── Estado de ejecución ────────────────────────────
    _in_cloud = pipeline_runner.is_cloud()

    if _in_cloud:
        # ── Cloud: GitHub Actions ──
        if pipeline_runner.cloud_configured():
            cloud_status = pipeline_runner.get_cloud_status()
            is_running = bool(cloud_status and cloud_status.get("status") == "running")

            if is_running:
                @st.fragment(run_every=10)
                def _live_cloud():
                    s = pipeline_runner.get_cloud_status()
                    if not s or s.get("status") != "running":
                        st.rerun()
                        return
                    st.info(
                        f"⏳ **Pipeline en ejecución** en GitHub Actions "
                        f"({s.get('gh_status', '')})"
                    )
                    url = s.get("html_url", "")
                    if url:
                        st.markdown(f"[🔗 Ver progreso en GitHub]({url})")

                _live_cloud()
                st.divider()
            elif cloud_status:
                icon = {"completed": "✅", "failed": "❌", "cancelled": "⛔"}.get(
                    cloud_status["status"], "❓"
                )
                url = cloud_status.get("html_url", "")
                with st.expander(
                    f"{icon} Última ejecución: {cloud_status['status']}",
                    expanded=False,
                ):
                    if url:
                        st.markdown(f"[🔗 Ver en GitHub Actions]({url})")
                    st.caption(
                        f"Creada: {cloud_status.get('created_at', '')} — "
                        f"Actualizada: {cloud_status.get('updated_at', '')}"
                    )
                    if cloud_status["status"] == "completed":
                        st.success("Los leads se importaron automáticamente.")
                st.divider()
        else:
            is_running = False
            st.info(
                "ℹ️ Configura `GITHUB_PAT` y `GITHUB_REPO` en los secrets "
                "de Streamlit para lanzar pipelines desde aquí."
            )
    else:
        # ── Local: subproceso ──
        run_status = pipeline_runner.get_status()
        is_running = bool(run_status and run_status.get("status") == "running")

        if is_running:
            @st.fragment(run_every=3)
            def _live_pipeline():
                s = pipeline_runner.get_status()
                if not s or s.get("status") != "running":
                    st.rerun()
                    return
                st.info(
                    f"⏳ **Pipeline en ejecución** — "
                    f"_{s.get('profile_nombre', '')}_ · {s.get('started', '')}"
                )
                _log = _html.escape(pipeline_runner.get_log_tail(100) or "(esperando salida...)")
                st.components.v1.html(
                    f'<pre style="height:280px;overflow-y:auto;margin:0;'
                    f'background:#0e1117;color:#fafafa;padding:1rem;'
                    f'border-radius:.5rem;font:14px/1.5 monospace"'
                    f' id="pl">{_log}</pre>'
                    f'<script>document.getElementById("pl").scrollTop=1e9</script>',
                    height=300,
                )
                if st.button("⛔ Cancelar", use_container_width=True, type="secondary"):
                    pipeline_runner.kill_current()
                    st.rerun()

            _live_pipeline()
            st.divider()

        elif run_status:
            status_val = run_status.get("status", "")
            profile_nombre = run_status.get("profile_nombre", "")
            icon = "✅" if status_val == "completed" else "❌"
            label = "completada" if status_val == "completed" else status_val
            finished = run_status.get("finished", "")

            with st.expander(f"{icon} Última ejecución: _{profile_nombre}_ · {finished}", expanded=False):
                st.code(pipeline_runner.get_log_tail(60), language=None, height=200)

                output_files = run_status.get("output_files", {})
                if output_files:
                    st.markdown("**📁 Archivos generados:**")
                    dl_cols = st.columns(len(output_files))
                    for col, (key, fpath) in zip(dl_cols, output_files.items()):
                        p = Path(fpath)
                        if p.exists():
                            mime = "application/json" if fpath.endswith(".json") else "text/csv"
                            col.download_button(
                                label=f"⬇️ {p.name}",
                                data=p.read_bytes(),
                                file_name=p.name,
                                mime=mime,
                                use_container_width=True,
                            )
                        else:
                            col.caption(f"_{p.name}_  (no generado)")

                col_import, col_clear = st.columns(2)
                if col_import.button("📥 Importar leads generados", use_container_width=True, type="primary"):
                    enriched_path = DATA_DIR / "leads_enriched.json"
                    raw_path = DATA_DIR / "leads_raw.json"
                    imported = 0
                    _import_origen = run_status.get("profile_nombre", profile_nombre)
                    if enriched_path.exists():
                        imported = import_from_json(enriched_path, perfil_origen=_import_origen)
                    elif raw_path.exists():
                        imported = import_from_json(raw_path, perfil_origen=_import_origen)
                    if imported:
                        st.success(f"✅ {imported} leads importados")
                    else:
                        st.info("No hay leads nuevos para importar")
                    _clear_cache()
                    st.rerun()
                if col_clear.button("🗑️ Limpiar estado", use_container_width=True):
                    pipeline_runner.clear_status()
                    st.rerun()

            st.divider()

    # ── Perfiles guardados ──────────────────────────────
    profiles = _c_get_scrap_profiles()
    edit_id = st.session_state.get("scrap_edit_id")

    st.caption("Configura los parámetros del scraper y guárdalos como perfiles reutilizables.")

    if profiles:
        st.markdown("### Perfiles guardados")
        for p in profiles:
            ciudades_str = ", ".join(p["ciudades"]) if p["ciudades"] else "todas"
            web_label = _WEB_LABELS.get(p["require_website"], p["require_website"])
            with st.expander(f"**{p['nombre']}** — {ciudades_str}"):
                col_a, col_b = st.columns(2)
                col_a.write(f"🔍 Query: `{p['search_query']}`")
                col_a.write(f"⭐ Min puntuación: **{p['min_rating']}**")
                col_a.write(f"💬 Min reseñas: **{p['min_reviews']}**")
                col_b.write(f"🌐 Web: **{web_label}**")
                col_b.write(f"📜 Max scrolls: **{p['max_scrolls']}**")
                _ai = p.get("auto_import", 1)
                col_b.write(f"📥 Auto-import: **{'Sí' if _ai else 'No'}**")

                st.divider()

                # Botones de acción en una sola fila
                _can_launch = (not _in_cloud) or pipeline_runner.cloud_configured()
                if _can_launch:
                    mode_label = st.selectbox(
                        "Modo de ejecución",
                        list(_MODE_OPTIONS.keys()),
                        key=f"mode_{p['id']}",
                    )
                    btn1, btn2, btn3 = st.columns(3)
                    if btn1.button(
                        "🚀 Lanzar",
                        key=f"launch_{p['id']}",
                        disabled=is_running,
                        use_container_width=True,
                        type="primary",
                    ):
                        try:
                            mode = _MODE_OPTIONS[mode_label]
                            if _in_cloud:
                                pipeline_runner.launch_cloud(dict(p), mode)
                                st.success("Pipeline disparada en GitHub Actions.")
                            else:
                                pipeline_runner.launch(dict(p), mode)
                                st.success("Pipeline iniciada en background.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al lanzar: {e}")
                    if btn2.button("✏️ Editar", key=f"edit_{p['id']}", use_container_width=True):
                        st.session_state["scrap_edit_id"] = p["id"]
                        st.rerun()
                    if btn3.button("🗑️ Eliminar", key=f"del_{p['id']}", use_container_width=True):
                        delete_scrap_profile(p["id"])
                        if st.session_state.get("scrap_edit_id") == p["id"]:
                            st.session_state.pop("scrap_edit_id", None)
                        _clear_cache()
                        st.rerun()

                    if is_running:
                        st.caption("⏳ Hay una pipeline en ejecución. Espera a que termine.")
                else:
                    btn1, btn2 = st.columns(2)
                    if btn1.button("✏️ Editar", key=f"edit_{p['id']}", use_container_width=True):
                        st.session_state["scrap_edit_id"] = p["id"]
                        st.rerun()
                    if btn2.button("🗑️ Eliminar", key=f"del_{p['id']}", use_container_width=True):
                        delete_scrap_profile(p["id"])
                        if st.session_state.get("scrap_edit_id") == p["id"]:
                            st.session_state.pop("scrap_edit_id", None)
                        _clear_cache()
                        st.rerun()
    else:
        st.info("No hay perfiles guardados aún. Crea uno abajo.")

    st.divider()

    # ── Formulario crear / editar ───────────────────────
    editing = get_scrap_profile(edit_id) if edit_id else None
    form_title = f"✏️ Editando: {editing['nombre']}" if editing else "➕ Nuevo perfil"
    st.markdown(f"### {form_title}")

    with st.form("scrap_profile_form", clear_on_submit=False):
        f_nombre = st.text_input(
            "Nombre del perfil",
            value=editing["nombre"] if editing else "",
            placeholder="Ej: Clínicas premium con web",
        )
        f_query = st.text_input(
            "Query de búsqueda  (usa {city} como placeholder)",
            value=editing["search_query"] if editing else "Clínica de psicología en {city}",
            help="Se reemplaza {city} por cada ciudad seleccionada.",
        )
        f_ciudades = st.multiselect(
            "Ciudades",
            options=_CITIES_OPTIONS,
            default=editing["ciudades"] if editing else _CITIES_OPTIONS[:4],
            help="Vacío = usa todas las ciudades del config.py",
        )

        col1, col2 = st.columns(2)
        f_rating = col1.slider(
            "Puntuación mínima (★)",
            min_value=0.0, max_value=5.0, step=0.1,
            value=float(editing["min_rating"]) if editing else 4.0,
        )
        f_reviews = col2.slider(
            "Reseñas mínimas",
            min_value=0, max_value=500, step=5,
            value=int(editing["min_reviews"]) if editing else 20,
        )

        col3, col4 = st.columns(2)
        web_default = _WEB_LABELS.get(editing["require_website"], list(_WEB_OPTIONS.keys())[0]) if editing else list(_WEB_OPTIONS.keys())[0]
        f_web_label = col3.selectbox("Filtro de sitio web", list(_WEB_OPTIONS.keys()), index=list(_WEB_OPTIONS.keys()).index(web_default))
        f_scrolls = col4.slider(
            "Max scrolls",
            min_value=5, max_value=50, step=5,
            value=int(editing["max_scrolls"]) if editing else 20,
        )

        f_auto_import = st.checkbox(
            "📥 Auto-importar leads a Turso al terminar",
            value=bool(editing["auto_import"]) if editing else True,
            help="Si está desactivado, los leads se quedan como artifacts en GitHub y se importan manualmente.",
        )

        submitted = st.form_submit_button("💾 Guardar perfil", type="primary", use_container_width=True)
        if submitted:
            if not f_nombre.strip():
                st.error("El nombre del perfil no puede estar vacío.")
            elif "{city}" not in f_query:
                st.error("La query debe contener {city}.")
            else:
                f_require_web = _WEB_OPTIONS[f_web_label]
                if editing:
                    update_scrap_profile(
                        editing["id"], f_nombre.strip(), f_query.strip(),
                        f_ciudades, f_reviews, f_rating, f_require_web, f_scrolls,
                        f_auto_import,
                    )
                    st.session_state.pop("scrap_edit_id", None)
                    st.success("✅ Perfil actualizado")
                else:
                    save_scrap_profile(
                        f_nombre.strip(), f_query.strip(),
                        f_ciudades, f_reviews, f_rating, f_require_web, f_scrolls,
                        f_auto_import,
                    )
                    st.success("✅ Perfil guardado")
                _clear_cache()
                st.rerun()

    if editing:
        if st.button("✖ Cancelar edición", use_container_width=True):
            st.session_state.pop("scrap_edit_id", None)
            st.rerun()
