"""Tab Guía — onboarding permanente y panel de control.

Este tab existe para responder en 30 segundos a "he estado tres semanas sin
entrar, ¿cómo iba esto?". No asume que recuerdes nada.
"""

from __future__ import annotations

import streamlit as st

from src.crm import pipeline_runner
from src.crm.db import (
    PIPELINE_STAGES, _is_cloud, save_app_link, update_app_link, delete_app_link,
)
from src.crm.views import _components as ui


# ======================================================
# 1 · FLUJO EN 4 PASOS
# ======================================================

_PASOS = [
    ("1️⃣ Buscar clínicas",
     "Tab **⚙️ Scrap** → abre un perfil guardado → **🚀 Lanzar** con "
     "*Pipeline completa*.",
     "El robot abre Google Maps, recoge las clínicas que cumplen tus filtros "
     "(estrellas, reseñas, si tienen web) y luego entra en la web de cada una "
     "a buscar el email. Tarda entre 5 y 30 minutos."),

    ("2️⃣ Esperar y revisar",
     "El estado sale arriba del tab Scrap. En cloud tienes el enlace "
     "**Ver progreso en GitHub**.",
     "Cuando termina, los leads entran solos en la base de datos (si el perfil "
     "tiene marcado *Guardar los leads al terminar*). Los repetidos no se "
     "duplican."),

    ("3️⃣ Trabajar el embudo",
     "Tab **📋 Kanban** → botones **→ Contactado** / **✖ Descartar**.",
     "Cada lead recorre las etapas de izquierda a derecha. El punto de color "
     "te dice si le puedes escribir: verde y amarillo sí, rojo no."),

    ("4️⃣ Consultar y exportar",
     "Tab **📊 Tabla** para verlo todo junto y descargar CSV · "
     "Tab **🔍 Detalle** para la ficha de un lead.",
     "Los filtros de la barra lateral afectan a Kanban, Tabla y Detalle a la vez."),
]


def _flujo():
    st.markdown("### 🚦 Cómo se usa esto, de principio a fin")
    for titulo, donde, explica in _PASOS:
        with st.container(border=True):
            st.markdown(f"**{titulo}**")
            st.markdown(donde)
            st.caption(explica)


# ======================================================
# 2 · CHULETA
# ======================================================

_CHULETA = [
    ("Conseguir clínicas nuevas", "⚙️ Scrap → Lanzar (Pipeline completa)"),
    ("Buscar emails de los leads que ya tengo", "⚙️ Scrap → Lanzar (Solo buscar emails)"),
    ("Cambiar ciudades o filtros de búsqueda", "⚙️ Scrap → Editar perfil"),
    ("Marcar un lead como contactado", "📋 Kanban → botón → Contactado"),
    ("Apuntar algo de un lead", "🔍 Detalle → Notas (se guarda al salir del recuadro)"),
    ("Sacar la lista de emails", "📊 Tabla → ⬇️ Descargar CSV"),
    ("Ver sólo los leads con email de verdad", "Barra lateral → Email → Con email directo"),
    ("Empezar de cero", "Barra lateral → ⚠️ Zona peligrosa → Vaciar leads"),
]


def _chuleta():
    st.markdown("### 🧭 Quiero… ¿dónde se hace?")
    st.dataframe(
        [{"Quiero…": q, "Dónde": d} for q, d in _CHULETA],
        use_container_width=True, hide_index=True,
    )


# ======================================================
# 3 · GLOSARIO
# ======================================================

_ETAPAS_EXPLICADAS = {
    "Nuevo": "Recién scrapeado. Nadie le ha escrito todavía.",
    "Contactado": "Ya le has enviado el primer correo.",
    "Respuesta": "Ha contestado algo, sea interés o dudas.",
    "Demo": "Hay una demo agendada o hecha.",
    "Cerrado": "Ha comprado PsycoERP.",
    "Descartado": "No encaja o ha dicho que no. Deja de aparecer en el trabajo diario.",
}


def _glosario():
    st.markdown("### 📖 Qué significa cada cosa")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Colores de los leads**")
        for icono, titulo, desc in ui.QUALITY_LEGEND:
            st.markdown(f"{icono} **{titulo}** — {desc}")
        st.caption(
            "El nombre del director también se guarda, pero acierta poco: "
            "no se usa para escribir correos, sólo para consultarlo tú."
        )

    with col2:
        st.markdown("**Etapas del embudo**")
        for etapa in PIPELINE_STAGES:
            st.markdown(f"**{etapa}** — {_ETAPAS_EXPLICADAS.get(etapa, '')}")

    with st.expander("Vocabulario del proyecto"):
        st.markdown("""
- **Lead** — una clínica de psicología candidata a comprar PsycoERP.
- **Perfil de búsqueda** — una configuración guardada del robot (qué buscar,
  en qué ciudades, con qué filtros). Se reutiliza cada vez que lanzas.
- **Scraper** — la parte que recorre Google Maps y recoge las clínicas.
- **Enricher** — la parte que entra en la web de cada clínica a buscar el email.
- **Pipeline** — scraper + enricher, uno detrás de otro.
- **Turso** — la base de datos en la nube. Es la que usa la app desplegada.
- **GitHub Actions** — el ordenador gratuito donde corre el robot cuando lanzas
  desde la web (tu portátil puede estar apagado).
- **Artifact** — fichero de resultados que GitHub guarda tras una ejecución.
  Sólo se generan si desactivas el guardado automático.
        """)


# ======================================================
# 4 · ESTADO DEL SISTEMA
# ======================================================

def _estado():
    st.markdown("### 📡 Estado del sistema ahora mismo")

    stats = ui.c_get_stats()
    en_cloud = _is_cloud()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Leads", stats["total"])
    col2.metric("Con email", stats["con_email"])
    col3.metric("Contactados", stats["por_etapa"].get("Contactado", 0))
    col4.metric("Cerrados", stats["por_etapa"].get("Cerrado", 0))

    filas = []

    filas.append({
        "Qué": "Base de datos",
        "Estado": "☁️ Turso (cloud)" if en_cloud else "💾 SQLite local",
        "Detalle": "Los cambios los ve todo el mundo" if en_cloud
                   else "Sólo en este ordenador — data/crm.db",
    })

    if pipeline_runner.is_cloud():
        if pipeline_runner.cloud_configured():
            s = pipeline_runner.get_cloud_status()
            if s and s.get("status") == "running":
                estado, detalle = "⏳ Ejecutándose", "Mira el tab Scrap"
            elif s:
                estado = {"completed": "✅ Terminó bien",
                          "failed": "❌ Falló",
                          "cancelled": "⛔ Cancelada"}.get(s["status"], s["status"])
                detalle = s.get("updated_at", "")
            else:
                estado, detalle = "😴 Parada", "Nunca lanzada desde aquí"
        else:
            estado, detalle = "⚠️ Sin configurar", "Faltan GITHUB_PAT / GITHUB_REPO en secrets"
    else:
        s = pipeline_runner.get_status()
        if s and s.get("status") == "running":
            estado, detalle = "⏳ Ejecutándose", s.get("profile_nombre", "")
        elif s:
            estado = "✅ Terminó bien" if s.get("status") == "completed" else "❌ Falló"
            detalle = s.get("finished", "")
        else:
            estado, detalle = "😴 Parada", "Nunca lanzada"
    filas.append({"Qué": "Robot de scraping", "Estado": estado, "Detalle": detalle})

    filas.append({
        "Qué": "Envío automático de correos",
        "Estado": "🚧 Pendiente",
        "Detalle": "Llega en la Fase 6 del plan",
    })

    st.dataframe(filas, use_container_width=True, hide_index=True)


# ======================================================
# 5 · ENLACES
# ======================================================

def _enlaces():
    st.markdown("### 🔗 Enlaces importantes")
    st.caption(
        "Todos los paneles externos de los que depende esto. "
        "Están guardados en la base de datos: edítalos aquí, sin tocar código."
    )

    links = ui.c_get_app_links()

    if not links:
        st.info("No hay enlaces guardados.")
    else:
        categorias = []
        for l in links:
            if l["categoria"] not in categorias:
                categorias.append(l["categoria"])

        for cat in categorias:
            st.markdown(f"**{cat}**")
            for l in [x for x in links if x["categoria"] == cat]:
                st.markdown(f"- [{l['titulo']}]({l['url']}) — {l['para_que']}")

    with st.expander("✏️ Gestionar enlaces"):
        st.caption("Añadir uno nuevo")
        with st.form("nuevo_link", clear_on_submit=True):
            c1, c2 = st.columns(2)
            n_cat = c1.text_input("Categoría", value="General")
            n_tit = c2.text_input("Título")
            n_url = st.text_input("URL", placeholder="https://…")
            n_para = st.text_input("¿Para qué sirve?")
            if st.form_submit_button("➕ Añadir", type="primary"):
                if not n_tit.strip() or not n_url.strip():
                    st.error("Título y URL son obligatorios.")
                else:
                    save_app_link(n_cat, n_tit, n_url, n_para)
                    ui.clear_cache()
                    st.rerun()

        if links:
            st.divider()
            st.caption("Editar o borrar uno existente")
            opciones = {f"{l['categoria']} · {l['titulo']}": l for l in links}
            sel = st.selectbox("Enlace", list(opciones.keys()), key="link_edit_sel")
            link = opciones[sel]
            with st.form(f"edit_link_{link['id']}"):
                c1, c2 = st.columns(2)
                e_cat = c1.text_input("Categoría", value=link["categoria"])
                e_tit = c2.text_input("Título", value=link["titulo"])
                e_url = st.text_input("URL", value=link["url"])
                e_para = st.text_input("¿Para qué sirve?", value=link["para_que"])
                b1, b2 = st.columns(2)
                if b1.form_submit_button("💾 Guardar", use_container_width=True):
                    update_app_link(link["id"], e_cat, e_tit, e_url, e_para,
                                    link["orden"])
                    ui.clear_cache()
                    st.rerun()
                if b2.form_submit_button("🗑️ Borrar", use_container_width=True):
                    delete_app_link(link["id"])
                    ui.clear_cache()
                    st.rerun()


# ======================================================
# 6 · MANTENIMIENTO
# ======================================================

def _mantenimiento():
    st.markdown("### ⚠️ Cosas que no puedes olvidar")
    st.warning("""
- **El repositorio de GitHub tiene que seguir siendo público.** En privado, los
  minutos de GitHub Actions se cobran y el robot dejaría de funcionar gratis.
- **GitHub desactiva las tareas programadas a los 60 días sin actividad** en el
  repo. Un commit cualquiera cada dos meses lo mantiene vivo.
- **Streamlit duerme la app a las 12 horas sin visitas.** Es normal: al entrar
  tarda unos segundos en despertar, no está rota.
- **La app debe estar en modo privado** (Streamlit → Settings → Sharing) para
  que los datos de las clínicas no sean públicos.
- **Revisa las cuotas gratuitas cada 6 meses.** Turso y GitHub pueden cambiar
  sus límites.
    """)


# ======================================================
# RENDER
# ======================================================

def render():
    st.markdown("## 👋 Guía rápida")
    st.caption(
        "Buscas clínicas de psicología, les sacas el email y las vas moviendo "
        "por el embudo hasta vender PsycoERP (2.500 € pago único)."
    )

    _estado()
    st.divider()
    _flujo()
    st.divider()
    _chuleta()
    st.divider()
    _glosario()
    st.divider()
    _enlaces()
    st.divider()
    _mantenimiento()
