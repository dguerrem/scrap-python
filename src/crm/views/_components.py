"""Piezas compartidas por las vistas: caché, callbacks y filtros.

Todo lo que más de un tab necesita vive aquí, para que las vistas sólo se
ocupen de dibujar.
"""

from __future__ import annotations

import streamlit as st

from src.crm.db import (
    get_all_leads, get_leads_by_stage, get_stats, get_scrap_profiles,
    get_app_links, update_lead_stage, update_lead_notes, PIPELINE_STAGES,
)

SIN_PERFIL = "(sin perfil)"


# ======================================================
# CACHÉ — evita repetir llamadas a Turso en cada rerun
# ======================================================

@st.cache_data(ttl=300)
def c_get_all_leads():
    return [dict(r) for r in get_all_leads()]


@st.cache_data(ttl=300)
def c_get_leads_by_stage(stage):
    return [dict(r) for r in get_leads_by_stage(stage)]


@st.cache_data(ttl=300)
def c_get_stats():
    return get_stats()


@st.cache_data(ttl=300)
def c_get_scrap_profiles():
    return get_scrap_profiles()


@st.cache_data(ttl=300)
def c_get_app_links():
    return get_app_links()


def clear_cache():
    st.cache_data.clear()


# ======================================================
# CALLBACKS DE GUARDADO
# ======================================================
# Streamlit re-ejecuta el script entero en cada interacción. Comparar el valor
# del widget contra el lead cacheado hacía que la condición siguiera siendo
# cierta tras guardar, disparando un UPDATE por rerun (ver BUG-4). Con
# on_change el callback corre una sola vez, justo cuando el valor cambia.

def on_notes_change(lead_id: int, widget_key: str):
    update_lead_notes(lead_id, st.session_state[widget_key])
    clear_cache()
    st.toast("Notas guardadas", icon="💾")


def on_stage_change(lead_id: int, widget_key: str):
    update_lead_stage(lead_id, st.session_state[widget_key])
    clear_cache()
    st.toast(f"Movido a {st.session_state[widget_key]}", icon="➡️")


def move_lead(lead_id: int, stage: str):
    """Mueve un lead de etapa desde un botón de acción rápida."""
    update_lead_stage(lead_id, stage)
    # Los selectores de etapa guardan su valor en session_state por lead. Si no
    # se limpian, seguirían mostrando la etapa vieja y al tocarlos devolverían
    # el lead a donde estaba.
    for k in (f"stage_{lead_id}", f"detail_stage_{lead_id}"):
        st.session_state.pop(k, None)
    clear_cache()
    st.toast(f"Movido a {stage}", icon="➡️")


# ======================================================
# CALIDAD DEL LEAD
# ======================================================
# El director NO puntúa: su tasa de acierto es baja y a veces devuelve el
# propio nombre de la clínica. El email es lo único que determina si el lead
# se puede usar para el envío.

QUALITY_LEGEND = [
    ("🟢", "Email directo", "Escribe a una persona concreta de la clínica"),
    ("🟡", "Sólo email genérico", "info@ / contacto@ — llega, pero a un buzón común"),
    ("🔴", "Sin email", "No se puede contactar por correo; sólo teléfono"),
]


def quality_icon(lead: dict) -> str:
    if lead.get("email_directo"):
        return "🟢"
    if lead.get("email_generico"):
        return "🟡"
    return "🔴"


def lead_email(lead: dict) -> str:
    return lead.get("email_directo") or lead.get("email_generico") or ""


def origen_de(lead: dict) -> str:
    return lead.get("perfil_origen") or SIN_PERFIL


# ======================================================
# FILTROS COMPARTIDOS
# ======================================================
# Se dibujan una sola vez en la barra lateral y los aplican tanto Kanban como
# Tabla. Antes cada tab tenía su propia fila de filtros: mismos controles
# repetidos y resultados distintos según dónde mirases.

EMAIL_FILTERS = ["Todos", "Con email directo", "Con email genérico", "Sin email"]


def render_filters(all_leads: list):
    """Dibuja los filtros en la barra lateral. Devuelve el dict de criterios."""
    ciudades = sorted({l["ciudad"] for l in all_leads if l["ciudad"]})
    origenes = sorted({origen_de(l) for l in all_leads})

    st.multiselect("Etapa", PIPELINE_STAGES, default=[], key="f_etapa",
                   placeholder="Todas", help="Sólo afecta a la Tabla; "
                   "en el Kanban la etapa es la columna.")
    st.multiselect("Ciudad", ciudades, default=[], key="f_ciudad",
                   placeholder="Todas")
    st.multiselect("Perfil de origen", origenes, default=[], key="f_origen",
                   placeholder="Todos")
    st.selectbox("Email", EMAIL_FILTERS, key="f_email")

    criterios = {
        "etapa": st.session_state.get("f_etapa") or list(PIPELINE_STAGES),
        "ciudad": st.session_state.get("f_ciudad") or ciudades,
        "origen": st.session_state.get("f_origen") or origenes,
        "email": st.session_state.get("f_email", "Todos"),
    }

    activos = sum([
        bool(st.session_state.get("f_etapa")),
        bool(st.session_state.get("f_ciudad")),
        bool(st.session_state.get("f_origen")),
        st.session_state.get("f_email", "Todos") != "Todos",
    ])
    if activos:
        st.caption(f"🔎 {activos} filtro(s) activo(s) — afectan a Kanban y Tabla")
        if st.button("Limpiar filtros", use_container_width=True):
            st.session_state["f_etapa"] = []
            st.session_state["f_ciudad"] = []
            st.session_state["f_origen"] = []
            st.session_state["f_email"] = "Todos"
            st.rerun()

    return criterios


def apply_filters(leads: list, criterios: dict, incluir_etapa: bool = False) -> list:
    """Aplica los criterios de la barra lateral a una lista de leads."""
    if not criterios:
        return leads

    out = [l for l in leads
           if l["ciudad"] in criterios["ciudad"]
           and origen_de(l) in criterios["origen"]]

    if incluir_etapa:
        out = [l for l in out if l["etapa"] in criterios["etapa"]]

    modo = criterios.get("email", "Todos")
    if modo == "Con email directo":
        out = [l for l in out if l["email_directo"]]
    elif modo == "Con email genérico":
        out = [l for l in out if l["email_generico"] and not l["email_directo"]]
    elif modo == "Sin email":
        out = [l for l in out if not l["email_directo"] and not l["email_generico"]]
    return out
