"""Tab Kanban — el pipeline de ventas en columnas."""

from __future__ import annotations

import streamlit as st

from src.crm.db import PIPELINE_STAGES, stage_index
from src.crm.views import _components as ui


# Atajos por etapa: el 90 % de los movimientos son "avanza uno" o "descarta".
# El selectbox completo sigue disponible para el resto.
_SIGUIENTE = {
    "Nuevo": "Contactado",
    "Contactado": "Respuesta",
    "Respuesta": "Demo",
    "Demo": "Cerrado",
}


def render(criterios: dict):
    st.caption(
        "Arrastra tus leads por el embudo. Usa los botones rápidos para avanzar "
        "o descartar sin abrir menús."
    )

    cols = st.columns(len(PIPELINE_STAGES))

    for i, stage in enumerate(PIPELINE_STAGES):
        with cols[i]:
            leads = ui.apply_filters(ui.c_get_leads_by_stage(stage), criterios)
            st.markdown(f"**{stage}**  ·  `{len(leads)}`")

            if not leads:
                st.caption("—")

            for lead in leads:
                quality = ui.quality_icon(lead)

                with st.expander(f"{quality} {lead['nombre'][:30]}"):
                    st.caption(
                        f"📍 {lead['ciudad']} · ⭐ {lead['puntuacion']} · 💬 {lead['resenas']}"
                    )
                    if lead.get("perfil_origen"):
                        st.caption(f"🎯 _{lead['perfil_origen']}_")

                    email = ui.lead_email(lead)
                    if lead["email_directo"]:
                        st.write(f"📧 {email}")
                    elif email:
                        st.write(f"📧 {email} *(genérico)*")
                    if lead["telefono"]:
                        st.write(f"📞 {lead['telefono']}")
                    if lead["sociedad"]:
                        st.caption(f"🏢 {lead['sociedad']}")

                    # ── Acciones rápidas ──
                    siguiente = _SIGUIENTE.get(stage)
                    acciones = st.columns(2 if siguiente else 1)
                    if siguiente:
                        acciones[0].button(
                            f"→ {siguiente}",
                            key=f"next_{lead['id']}",
                            use_container_width=True,
                            on_click=ui.move_lead,
                            args=(lead["id"], siguiente),
                        )
                    if stage != "Descartado":
                        acciones[-1].button(
                            "✖ Descartar",
                            key=f"drop_{lead['id']}",
                            use_container_width=True,
                            on_click=ui.move_lead,
                            args=(lead["id"], "Descartado"),
                        )

                    with st.popover("Más", use_container_width=True):
                        _k_stage = f"stage_{lead['id']}"
                        st.selectbox(
                            "Mover a",
                            PIPELINE_STAGES,
                            index=stage_index(stage),
                            key=_k_stage,
                            on_change=ui.on_stage_change,
                            args=(lead["id"], _k_stage),
                        )
                        _k_notas = f"notas_{lead['id']}"
                        st.text_area(
                            "Notas",
                            value=lead["notas"] or "",
                            key=_k_notas,
                            height=90,
                            on_change=ui.on_notes_change,
                            args=(lead["id"], _k_notas),
                        )
