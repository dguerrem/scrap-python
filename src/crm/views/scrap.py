"""Tab Scrap — perfiles de búsqueda y lanzamiento del pipeline."""

from __future__ import annotations

import html as _html
from pathlib import Path

import streamlit as st

from src.crm import pipeline_runner
from src.crm.db import (
    import_from_json, save_scrap_profile, get_scrap_profile,
    update_scrap_profile, delete_scrap_profile,
)
from src.crm.views import _components as ui

DATA_DIR = Path(__file__).resolve().parents[3] / "data"

CITIES_OPTIONS = [
    "Madrid", "Barcelona", "Valencia", "Sevilla", "Málaga",
    "Bilbao", "Zaragoza", "Murcia", "Palma de Mallorca",
    "Las Palmas de Gran Canaria",
]

WEB_OPTIONS = {
    "Solo con web (vender software)": "required",
    "Solo sin web (vender landing page)": "none",
    "Todos (sin filtro)": "any",
}
WEB_LABELS = {v: k for k, v in WEB_OPTIONS.items()}

MODE_OPTIONS = {
    "🚀 Pipeline completa (buscar + buscar emails)": "pipeline",
    "🗺️ Solo buscar clínicas (Google Maps)": "scraper",
    "🔍 Solo buscar emails de lo ya guardado": "enricher",
}


# ======================================================
# ESTADO DE EJECUCIÓN
# ======================================================

def _estado_cloud() -> bool:
    """Dibuja el estado en cloud. Devuelve True si hay algo corriendo."""
    if not pipeline_runner.cloud_configured():
        st.info(
            "ℹ️ Configura `GITHUB_PAT` y `GITHUB_REPO` en los secrets de "
            "Streamlit para poder lanzar pipelines desde aquí."
        )
        return False

    cloud_status = pipeline_runner.get_cloud_status()
    is_running = bool(cloud_status and cloud_status.get("status") == "running")

    if is_running:
        @st.fragment(run_every=10)
        def _live_cloud():
            s = pipeline_runner.get_cloud_status()
            if not s or s.get("status") != "running":
                ui.clear_cache()
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
        return True

    if cloud_status:
        # La pipeline terminó — limpiar caché para reflejar los nuevos leads
        if "cloud_cache_cleared" not in st.session_state:
            ui.clear_cache()
            st.session_state["cloud_cache_cleared"] = True

        icon = {"completed": "✅", "failed": "❌", "cancelled": "⛔"}.get(
            cloud_status["status"], "❓"
        )
        url = cloud_status.get("html_url", "")
        with st.expander(f"{icon} Última ejecución: {cloud_status['status']}"):
            if url:
                st.markdown(f"[🔗 Ver logs en GitHub Actions]({url})")
            st.caption(
                f"Creada: {cloud_status.get('created_at', '')} — "
                f"Actualizada: {cloud_status.get('updated_at', '')}"
            )
            if cloud_status["status"] == "completed":
                st.success("Los leads se importaron automáticamente.")
            elif cloud_status["status"] == "failed":
                st.warning("La pipeline falló. Revisa los logs en GitHub Actions.")
    return False


def _estado_local() -> bool:
    """Dibuja el estado en local. Devuelve True si hay algo corriendo."""
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
        return True

    if run_status:
        status_val = run_status.get("status", "")
        profile_nombre = run_status.get("profile_nombre", "")
        icon = "✅" if status_val == "completed" else "❌"
        finished = run_status.get("finished", "")

        with st.expander(f"{icon} Última ejecución: _{profile_nombre}_ · {finished}"):
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
            if col_import.button("📥 Importar leads generados",
                                 use_container_width=True, type="primary"):
                enriched_path = DATA_DIR / "leads_enriched.json"
                raw_path = DATA_DIR / "leads_raw.json"
                imported = 0
                _origen = run_status.get("profile_nombre", profile_nombre)
                if enriched_path.exists():
                    imported = import_from_json(enriched_path, perfil_origen=_origen)
                elif raw_path.exists():
                    imported = import_from_json(raw_path, perfil_origen=_origen)
                if imported:
                    st.success(f"✅ {imported} leads importados")
                else:
                    st.info("No hay leads nuevos para importar")
                ui.clear_cache()
                st.rerun()
            if col_clear.button("🗑️ Limpiar estado", use_container_width=True):
                pipeline_runner.clear_status()
                st.rerun()
    return False


# ======================================================
# PERFILES
# ======================================================

def _perfiles(in_cloud: bool, is_running: bool):
    profiles = ui.c_get_scrap_profiles()

    if not profiles:
        st.info("No hay perfiles guardados. Crea uno en **➕ Crear perfil**, abajo.")
        return

    puede_lanzar = (not in_cloud) or pipeline_runner.cloud_configured()

    for p in profiles:
        ciudades_str = ", ".join(p["ciudades"]) if p["ciudades"] else "todas"
        with st.expander(f"**{p['nombre']}** — {ciudades_str}"):
            col_a, col_b = st.columns(2)
            col_a.caption(f"🔍 `{p['search_query']}`")
            col_a.caption(f"⭐ ≥ {p['min_rating']}  ·  💬 ≥ {p['min_reviews']}")
            col_b.caption(f"🌐 {WEB_LABELS.get(p['require_website'], p['require_website'])}")
            col_b.caption(
                f"📜 {p['max_scrolls']} scrolls  ·  "
                f"📥 auto-import: {'sí' if p.get('auto_import', 1) else 'no'}"
            )

            if puede_lanzar:
                mode_label = st.selectbox(
                    "¿Qué quieres ejecutar?",
                    list(MODE_OPTIONS.keys()),
                    key=f"mode_{p['id']}",
                )
                if st.button(
                    "🚀 Lanzar",
                    key=f"launch_{p['id']}",
                    disabled=is_running,
                    use_container_width=True,
                    type="primary",
                ):
                    try:
                        mode = MODE_OPTIONS[mode_label]
                        if in_cloud:
                            pipeline_runner.launch_cloud(dict(p), mode)
                            st.session_state.pop("cloud_cache_cleared", None)
                            st.success("Pipeline disparada en GitHub Actions.")
                        else:
                            pipeline_runner.launch(dict(p), mode)
                            st.success("Pipeline iniciada en background.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al lanzar: {e}")
                if is_running:
                    st.caption("⏳ Ya hay una pipeline en ejecución. Espera a que termine.")

            col_e, col_d = st.columns(2)
            if col_e.button("✏️ Editar", key=f"edit_{p['id']}", use_container_width=True):
                st.session_state["scrap_edit_id"] = p["id"]
                st.rerun()
            if col_d.button("🗑️ Eliminar", key=f"del_{p['id']}", use_container_width=True):
                delete_scrap_profile(p["id"])
                if st.session_state.get("scrap_edit_id") == p["id"]:
                    st.session_state.pop("scrap_edit_id", None)
                ui.clear_cache()
                st.rerun()


def _formulario():
    edit_id = st.session_state.get("scrap_edit_id")
    editing = get_scrap_profile(edit_id) if edit_id else None

    with st.form("scrap_profile_form", clear_on_submit=False):
        f_nombre = st.text_input(
            "Nombre del perfil",
            value=editing["nombre"] if editing else "",
            placeholder="Ej: Clínicas premium con web",
        )
        f_query = st.text_input(
            "Qué buscar en Google Maps  (usa {city} como comodín)",
            value=editing["search_query"] if editing else "Clínica de psicología en {city}",
            help="Se reemplaza {city} por cada ciudad seleccionada.",
        )
        f_ciudades = st.multiselect(
            "Ciudades",
            options=CITIES_OPTIONS,
            default=editing["ciudades"] if editing else CITIES_OPTIONS[:4],
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
        web_default = (WEB_LABELS.get(editing["require_website"], list(WEB_OPTIONS)[0])
                       if editing else list(WEB_OPTIONS)[0])
        f_web_label = col3.selectbox(
            "Filtro de sitio web", list(WEB_OPTIONS.keys()),
            index=list(WEB_OPTIONS.keys()).index(web_default),
        )
        f_scrolls = col4.slider(
            "Max scrolls",
            min_value=5, max_value=50, step=5,
            value=int(editing["max_scrolls"]) if editing else 20,
            help="Cuántas veces baja la página de resultados. Más scrolls = "
                 "más clínicas y más tiempo de ejecución.",
        )

        f_auto_import = st.checkbox(
            "📥 Guardar los leads en la base de datos al terminar",
            value=bool(editing["auto_import"]) if editing else True,
            help="Si lo desactivas, los resultados se quedan en GitHub como "
                 "artifacts y hay que importarlos a mano.",
        )

        submitted = st.form_submit_button(
            "💾 Guardar cambios" if editing else "💾 Crear perfil",
            type="primary", use_container_width=True,
        )
        if submitted:
            if not f_nombre.strip():
                st.error("El nombre del perfil no puede estar vacío.")
            elif "{city}" not in f_query:
                st.error("La query debe contener {city}.")
            else:
                f_require_web = WEB_OPTIONS[f_web_label]
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
                ui.clear_cache()
                st.rerun()

    if editing and st.button("Cancelar edición"):
        st.session_state.pop("scrap_edit_id", None)
        st.rerun()


# ======================================================
# RENDER
# ======================================================

def render():
    in_cloud = pipeline_runner.is_cloud()

    # El estado de ejecución va fijo arriba: es lo primero que quieres saber
    # al entrar en este tab.
    is_running = _estado_cloud() if in_cloud else _estado_local()

    st.divider()

    editando = bool(st.session_state.get("scrap_edit_id"))

    st.markdown("### 📁 Perfiles guardados")
    st.caption("Una búsqueda guardada = un perfil. Ábrelo y pulsa Lanzar.")
    _perfiles(in_cloud, is_running)

    st.divider()

    with st.expander("✏️ Editando perfil" if editando else "➕ Crear perfil",
                     expanded=editando):
        _formulario()
