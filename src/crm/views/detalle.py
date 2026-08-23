"""Tab Detalle — ficha completa de un lead."""

from __future__ import annotations

import streamlit as st

from src.crm.db import PIPELINE_STAGES, stage_index
from src.crm.views import _components as ui


def render(criterios: dict):
    all_leads = ui.apply_filters(ui.c_get_all_leads(), criterios, incluir_etapa=True)

    if not all_leads:
        st.info("No hay leads que encajen con los filtros de la barra lateral.")
        return

    lead_names = [f"{ui.quality_icon(l)} {l['nombre']} ({l['ciudad']})" for l in all_leads]
    selected = st.selectbox("Seleccionar lead", lead_names, key="detail_lead")

    if not selected:
        return

    idx = lead_names.index(selected)
    lead = all_leads[idx]

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader(lead["nombre"])

        email = ui.lead_email(lead)
        if email:
            tipo = "directo" if lead["email_directo"] else "genérico"
            st.markdown(f"### 📧 {email}")
            st.caption(f"Email {tipo} — es el dato que usa el mailer")
        else:
            st.warning("Sin email. Este lead no entra en los envíos automáticos.")

        st.write(f"📞 **Teléfono:** {lead['telefono'] or '—'}")
        st.write(f"📍 **Ciudad:** {lead['ciudad']}")
        st.write(f"📫 **Dirección:** {lead['direccion'] or '—'}")
        if lead["url"]:
            st.write(f"🌐 **Web:** {lead['url']}")
        st.write(f"⭐ **Puntuación:** {lead['puntuacion']}  ·  💬 **Reseñas:** {lead['resenas']}")

        with st.expander("Datos secundarios"):
            st.write(f"👤 **Director:** {lead['director'] or '—'}")
            st.caption(
                "El director se extrae de la web y acierta poco: se guarda para "
                "consulta manual, pero **no** se usa en los correos."
            )
            st.write(f"🏢 **Sociedad:** {lead['sociedad'] or '—'}")
            st.write(f"🎯 **Perfil origen:** {lead.get('perfil_origen') or '—'}")
            st.write(f"📧 **Email genérico:** {lead['email_generico'] or '—'}")

    with col2:
        st.markdown("**Pipeline**")
        # Clave por lead: con una clave fija ("detail_stage"), Streamlit
        # conserva el valor al cambiar de lead y lo escribiría sobre el
        # lead siguiente.
        _k_stage = f"detail_stage_{lead['id']}"
        st.selectbox(
            "Etapa actual",
            PIPELINE_STAGES,
            index=stage_index(lead["etapa"]),
            key=_k_stage,
            on_change=ui.on_stage_change,
            args=(lead["id"], _k_stage),
        )

        _k_notas = f"detail_notas_{lead['id']}"
        st.text_area(
            "Notas",
            value=lead["notas"] or "",
            height=220,
            key=_k_notas,
            on_change=ui.on_notes_change,
            args=(lead["id"], _k_notas),
        )
        st.caption("Se guardan al salir del recuadro.")
