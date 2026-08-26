"""Tab Emails — panel de control del mailer."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from src.mailer import autonomy, config, scheduler, store, templates
from src.crm.views import _components as ui


# ======================================================
# PANEL DE CONTROL
# ======================================================

def _panel(st_estado: dict):
    modos = st_estado["modos_prueba"]
    if modos:
        st.warning("🧪 **Modo de prueba activo:** " + " · ".join(modos))

    listo, motivo = config.smtp_listo()
    if not listo and not config.dry_run():
        st.error(
            f"SMTP sin configurar ({motivo}). Añade `SMTP_USER` y "
            "`SMTP_APP_PASSWORD` en los secrets antes de encender."
        )

    col1, col2 = st.columns([1, 3])

    with col1:
        encendido = st.toggle(
            "Mailer encendido",
            value=st_estado["activo"],
            key="mailer_activo",
            help="Interruptor maestro. Al encenderlo por primera vez arranca "
                 "el calentamiento del dominio.",
        )
        if encendido != st_estado["activo"]:
            scheduler.activar(encendido)
            ui.clear_cache()
            st.rerun()

    with col2:
        dia = st_estado["dia_warmup"]
        partes = [
            "🟢 Activo" if st_estado["activo"] else "⚪ Apagado",
            f"día {dia} de calentamiento" if dia is not None else "sin calentar",
            f"hoy {st_estado['enviados_hoy']}/{st_estado['tope_diario']}",
        ]
        if not st_estado["ventana_abierta"]:
            partes.append(f"⏸️ {st_estado['motivo_ventana']}")
        elif not st_estado["toca_enviar"]:
            partes.append(f"⏳ {st_estado['motivo_hueco']}")
        st.markdown("### " + "  ·  ".join(partes))
        st.caption(
            f"Cola: {st_estado['pendientes']} pendientes · "
            f"{st_estado['enviados_total']} enviados · "
            f"{st_estado['fallidos']} fallidos  |  "
            f"Último envío: {st_estado['ultimo_envio'] or 'nunca'}"
        )

    if st_estado["tasa_fallos"] > 0.05:
        st.error(
            f"Tasa de fallos del {st_estado['tasa_fallos'] * 100:.0f}% en los "
            "últimos 7 días. La rampa se ha congelado sola. Revisa las "
            "credenciales antes de seguir."
        )

    c1, c2 = st.columns(2)
    if c1.button("📤 Enviar 1 ahora", use_container_width=True, type="primary",
                 help="Salta el horario y el ritmo, pero nunca el ledger."):
        resultado = scheduler.tick(forzar=True)
        accion = resultado.get("accion")
        if accion == "sent":
            st.success(f"✅ {resultado['detalle']}")
        elif accion == "failed":
            st.error(f"❌ {resultado['error']}")
        elif accion == "skipped":
            st.info("○ Saltado: ese dominio ya estaba contactado o suprimido.")
        else:
            st.info(f"Sin acción: {resultado.get('motivo', '')}")
        ui.clear_cache()

    if c2.button("♻️ Reintentar fallidos", use_container_width=True):
        n = store.reintentar_fallidos()
        st.success(f"{n} vuelven a la cola") if n else st.info("No hay fallidos")
        ui.clear_cache()
        st.rerun()


# ======================================================
# AUTONOMÍA
# ======================================================

def _autonomia():
    datos = autonomy.resumen()

    c1, c2, c3 = st.columns(3)
    c1.metric("📬 Contactables", datos["contactables"])
    c2.metric("📤 Ritmo", f"{datos['tope_diario']}/día")
    c3.metric("⏳ Autonomía", f"{datos['dias_autonomia']} días")

    if datos["dias_autonomia"] < store.get_int("aviso_umbral_dias", 3):
        st.warning(
            "Te estás quedando sin contactos. Lanza un scrap nuevo en el tab "
            "⚙️ Scrap, o baja el filtro de reseñas para ampliar la búsqueda."
        )

    if datos["por_ciudad"]:
        st.caption("Disponibles por ciudad")
        st.dataframe(
            [{"Ciudad": c, "Disponibles": n} for c, n in datos["por_ciudad"].items()],
            use_container_width=True, hide_index=True, height=200,
        )
    if datos["ciudades_agotadas"]:
        st.caption("🪫 Agotadas: " + ", ".join(datos["ciudades_agotadas"]))


# ======================================================
# ENCOLADO
# ======================================================

def _encolar():
    disponibles = autonomy.contactables()
    if not disponibles:
        st.info("No hay contactos disponibles. Todo enviado, vetado o sin email.")
        return

    ciudades = sorted({l.get("ciudad") or "(sin ciudad)" for l in disponibles})
    perfiles = sorted({l.get("perfil_origen") or "(sin perfil)" for l in disponibles})

    with st.form("mail_q_filtros"):
        c1, c2, c3 = st.columns(3)
        f_ciudad = c1.multiselect("Ciudad", ciudades, placeholder="Todas",
                                  key="mail_q_ciudad")
        f_perfil = c2.multiselect("Perfil", perfiles, placeholder="Todos",
                                  key="mail_q_perfil")
        f_calidad = c3.selectbox("Calidad", ["Todos", "Sólo email directo"],
                                 key="mail_q_calidad")
        st.form_submit_button("Aplicar filtros")

    seleccion = [
        l for l in disponibles
        if (not f_ciudad or (l.get("ciudad") or "(sin ciudad)") in f_ciudad)
        and (not f_perfil or (l.get("perfil_origen") or "(sin perfil)") in f_perfil)
        and (f_calidad == "Todos" or l.get("email_directo"))
    ]
    # Los de email directo primero: llegan a quien decide.
    seleccion.sort(key=lambda l: (not l.get("email_directo"), l["nombre"]))

    if not seleccion:
        st.info("No hay contactos que encajen con esos filtros.")
        return

    max_cantidad = len(seleccion)
    cantidad_guardada = st.session_state.get("mail_q_cantidad")
    if cantidad_guardada is not None and not 1 <= cantidad_guardada <= max_cantidad:
        st.session_state["mail_q_cantidad"] = max_cantidad
    if max_cantidad == 1:
        st.session_state["mail_q_cantidad"] = 1
        cantidad = 1
    else:
        cantidad = st.slider("Cuántos encolar", 1, max_cantidad,
                             min(10, max_cantidad), key="mail_q_cantidad")

    st.caption(
        f"Encajan **{len(seleccion)}** contactos con esos filtros. "
        f"Se encolarían los **{min(cantidad, len(seleccion))}** primeros."
    )

    if not store.plantilla_activa():
        st.warning("No hay plantilla activa. Créala abajo antes de encolar.")
        return

    if st.button("➕ Añadir a la cola", type="primary", use_container_width=True):
        try:
            res = autonomy.encolar_leads(seleccion[:cantidad])
            st.success(f"✅ {res['encolados']} encolados · {res['saltados']} saltados")
            ui.clear_cache()
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo encolar: {e}")


# ======================================================
# COLA
# ======================================================

def _cola():
    filas = store.cola(limite=300)
    if not filas:
        st.info("La cola está vacía.")
        return

    st.dataframe(
        [{
            "Estado": {"pending": "⏳", "sending": "📤", "sent": "✅",
                       "failed": "❌", "skipped": "○"}.get(f["estado"], f["estado"]),
            "Destinatario": f["destinatario"],
            "Asunto": f["asunto"],
            "Intentos": f["intentos"],
            "Error": (f["error"] or "")[:60],
        } for f in filas],
        use_container_width=True, hide_index=True,
    )

    pendientes = [f for f in filas if f["estado"] in ("pending", "failed")]
    if pendientes:
        etiquetas = {f"{f['destinatario']} ({f['estado']})": f for f in pendientes}
        sel = st.selectbox("Gestionar uno", list(etiquetas.keys()), key="mail_cola_sel")
        item = etiquetas[sel]
        c1, c2 = st.columns(2)
        if c1.button("🗑️ Quitar de la cola", use_container_width=True):
            store.borrar_de_cola(item["id"])
            ui.clear_cache()
            st.rerun()
        if c2.button("🚫 Quitar y no escribir nunca", use_container_width=True):
            store.suprimir(item["dominio"], item["destinatario"], "manual")
            store.borrar_de_cola(item["id"])
            ui.clear_cache()
            st.rerun()


# ======================================================
# PLANTILLAS
# ======================================================

def _plantillas():
    st.caption(
        "Variables disponibles: **{nombre}** y **{ciudad}**. El pie de baja se "
        "añade solo a todos los mensajes: es obligatorio por ley y mejora la "
        "entregabilidad."
    )

    lista = store.plantillas()
    activa = store.plantilla_activa()

    if lista:
        etiquetas = {
            f"{'⭐ ' if p['activa'] else ''}{p['nombre']}": p for p in lista
        }
        sel = st.selectbox("Plantilla", list(etiquetas.keys()), key="mail_tpl_sel")
        elegida = etiquetas[sel]
    else:
        elegida = None
        st.info("No hay plantillas. Crea la primera abajo.")

    with st.form("form_plantilla"):
        nombre = st.text_input("Nombre", value=elegida["nombre"] if elegida else "")
        asunto = st.text_input(
            "Asunto",
            value=elegida["asunto"] if elegida else "Una duda sobre {nombre}",
        )
        cuerpo = st.text_area(
            "Cuerpo",
            value=elegida["cuerpo"] if elegida else templates.PLANTILLA_PRUEBA["cuerpo"],
            height=220,
        )
        c1, c2, c3 = st.columns(3)
        guardar = c1.form_submit_button("💾 Guardar", use_container_width=True)
        nueva = c2.form_submit_button("➕ Crear nueva", use_container_width=True)
        activar = c3.form_submit_button("⭐ Usar esta", use_container_width=True,
                                        type="primary")

        if guardar or nueva:
            problemas = templates.validar(asunto, cuerpo)
            if not nombre.strip():
                problemas.append("Ponle un nombre a la plantilla.")
            if problemas:
                for p in problemas:
                    st.error(p)
            else:
                store.guardar_plantilla(
                    nombre, asunto, cuerpo,
                    elegida["id"] if (guardar and elegida) else None,
                )
                ui.clear_cache()
                st.rerun()

        if activar and elegida:
            store.activar_plantilla(elegida["id"])
            ui.clear_cache()
            st.rerun()

    if elegida and len(lista) > 1 and st.button("🗑️ Borrar plantilla"):
        store.borrar_plantilla(elegida["id"])
        ui.clear_cache()
        st.rerun()

    # ── Vista previa con un lead real ──
    st.divider()
    st.markdown("**Vista previa**")
    leads = ui.c_get_all_leads()
    con_email = [l for l in leads if l["email_directo"] or l["email_generico"]]
    if not con_email or not elegida:
        st.caption("Hace falta al menos un lead con email y una plantilla.")
        return

    nombres = [f"{l['nombre']} ({l['ciudad']})" for l in con_email]
    idx = nombres.index(st.selectbox("Con este lead", nombres, key="mail_preview_lead"))
    try:
        asunto_r, texto_r, html_r = autonomy.previsualizar(con_email[idx], elegida)
        st.text_input("Asunto renderizado", value=asunto_r, disabled=True,
                      key="mail_preview_asunto")
        tab_html, tab_texto = st.tabs(["Como se ve", "Texto plano"])
        with tab_html:
            components.html(html_r, height=340, scrolling=True)
        with tab_texto:
            st.code(texto_r, language=None)
    except Exception as e:
        st.error(f"La plantilla no se puede renderizar: {e}")


# ======================================================
# AJUSTES
# ======================================================

def _ajustes():
    ajustes = store.all_settings()

    with st.form("form_ajustes_mailer"):
        st.caption("Ritmo y volumen")
        c1, c2, c3 = st.columns(3)
        v_inicio = c1.number_input("Hora de inicio", 0, 23,
                                   int(ajustes.get("ventana_inicio") or 8))
        v_fin = c2.number_input("Hora de fin", 1, 24,
                                int(ajustes.get("ventana_fin") or 15))
        tope_max = c3.number_input("Tope máximo diario", 1, 200,
                                   int(ajustes.get("tope_maximo") or 45))

        c4, c5, c6 = st.columns(3)
        int_min = c4.number_input("Minutos mínimos entre envíos", 1, 120,
                                  int(ajustes.get("intervalo_min_min") or 5))
        int_max = c5.number_input("Minutos máximos entre envíos", 1, 240,
                                  int(ajustes.get("intervalo_max_min") or 15))
        tope_manual = c6.text_input(
            "Tope manual (vacío = rampa)", value=ajustes.get("tope_manual", ""),
            help="Ponlo a 2 para la prueba de humo en producción.",
        )

        st.caption("Firma — no la pongas en el código: el repositorio es público")
        firma_texto = st.text_area("Firma en texto plano",
                                   value=ajustes.get("firma_texto", ""), height=100)
        firma_html = st.text_area("Firma en HTML",
                                  value=ajustes.get("firma_html", ""), height=140)

        st.caption("Avisos")
        c7, c8 = st.columns(2)
        avisos = c7.text_input("Correos de aviso (separados por comas)",
                               value=ajustes.get("aviso_emails", ""))
        umbral = c8.number_input("Avisar cuando queden menos de X días", 1, 30,
                                 int(ajustes.get("aviso_umbral_dias") or 3))

        if st.form_submit_button("💾 Guardar ajustes", type="primary",
                                 use_container_width=True):
            if v_fin <= v_inicio:
                st.error("La hora de fin tiene que ser mayor que la de inicio.")
            elif int_max < int_min:
                st.error("El intervalo máximo no puede ser menor que el mínimo.")
            else:
                for clave, valor in [
                    ("ventana_inicio", v_inicio), ("ventana_fin", v_fin),
                    ("tope_maximo", tope_max), ("intervalo_min_min", int_min),
                    ("intervalo_max_min", int_max),
                    ("tope_manual", tope_manual.strip()),
                    ("firma_texto", firma_texto), ("firma_html", firma_html),
                    ("aviso_emails", avisos), ("aviso_umbral_dias", umbral),
                ]:
                    store.set_setting(clave, valor)
                st.success("Ajustes guardados")
                ui.clear_cache()
                st.rerun()

    with st.expander("🚫 Dominios que nunca recibirán correo"):
        suprimidos = store.listar_supresion()
        if suprimidos:
            st.dataframe(
                [{"Dominio": s["dominio"], "Motivo": s["motivo"],
                  "Desde": s["created_at"]} for s in suprimidos],
                use_container_width=True, hide_index=True,
            )
            quitar = st.selectbox("Quitar de la lista",
                                  [s["dominio"] for s in suprimidos],
                                  key="mail_sup_sel")
            if st.button("Quitar de la lista negra"):
                store.quitar_supresion(quitar)
                ui.clear_cache()
                st.rerun()
        else:
            st.caption("Ninguno todavía.")

        nuevo = st.text_input("Añadir dominio o email a la lista negra",
                              key="mail_sup_nuevo")
        if st.button("Añadir") and nuevo.strip():
            dominio = store.dominio_de(nuevo) or nuevo.strip().lower()
            store.suprimir(dominio, nuevo.strip(), "manual")
            ui.clear_cache()
            st.rerun()


# ======================================================
# HISTORIAL
# ======================================================

def _historial():
    filas = store.historial(200)
    if filas:
        st.dataframe(
            [{"Fecha": f["enviado_at"], "Clínica": f.get("nombre") or "—",
              "Ciudad": f.get("ciudad") or "—", "Email": f["email"]}
             for f in filas],
            use_container_width=True, hide_index=True,
        )
    else:
        st.caption("Todavía no se ha enviado nada.")

    with st.expander("Registro técnico"):
        logs = store.ultimos_logs(80)
        if logs:
            st.dataframe(
                [{"Cuándo": l["created_at"], "Evento": l["evento"],
                  "Detalle": (l["detalle"] or "")[:80]} for l in logs],
                use_container_width=True, hide_index=True,
            )
        else:
            st.caption("Sin eventos.")


# ======================================================
# RENDER
# ======================================================

def render():
    st_estado = scheduler.estado()
    _panel(st_estado)

    st.divider()

    tabs = st.tabs(["📊 Autonomía", "➕ Encolar", "📋 Cola", "✏️ Plantillas",
                    "⚙️ Ajustes", "🕘 Historial"])
    with tabs[0]:
        _autonomia()
    with tabs[1]:
        _encolar()
    with tabs[2]:
        _cola()
    with tabs[3]:
        _plantillas()
    with tabs[4]:
        _ajustes()
    with tabs[5]:
        _historial()
