"""Tab Tabla — vista de lista para revisar y exportar."""

from __future__ import annotations

import csv
import io

import streamlit as st

from src.crm.views import _components as ui


def _to_csv(rows: list) -> bytes:
    if not rows:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def render(criterios: dict):
    all_leads = ui.c_get_all_leads()

    if not all_leads:
        st.info("No hay leads todavía. Ve al tab **📖 Guía** para saber por dónde empezar.")
        return

    filtered = ui.apply_filters(all_leads, criterios, incluir_etapa=True)

    st.caption("Los filtros están en la barra lateral. Ordena pulsando en las columnas.")

    display_data = []
    for l in filtered:
        display_data.append({
            "": ui.quality_icon(l),
            "Nombre": l["nombre"],
            "Ciudad": l["ciudad"],
            "⭐": l["puntuacion"],
            "💬": l["resenas"],
            "Email": ui.lead_email(l) or "—",
            "Teléfono": l["telefono"] or "—",
            "Etapa": l["etapa"],
            "Origen": l.get("perfil_origen") or "—",
        })

    col_a, col_b = st.columns([3, 1])
    col_a.markdown(f"**{len(filtered)}** de {len(all_leads)} leads")
    col_b.download_button(
        "⬇️ Descargar CSV",
        data=_to_csv(display_data),
        file_name="leads.csv",
        mime="text/csv",
        use_container_width=True,
        disabled=not display_data,
    )

    st.dataframe(display_data, use_container_width=True, hide_index=True)
