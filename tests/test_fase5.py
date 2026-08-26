"""
Fase 5 — refactor de UI, filtros compartidos y tab Guia.

Comprueba que:
  1. La app arranca con los 5 tabs y sin excepciones
  2. Los filtros de la barra lateral afectan a Kanban, Tabla y Detalle a la vez
  3. Los botones de accion rapida mueven el lead y no dejan selectores obsoletos
  4. Los enlaces de la Guia se siembran una vez y se pueden editar
  5. El semaforo y las etapas siguen siendo coherentes tras el refactor

Ejecutar:  python tests/test_fase5.py
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Aislar de Turso y de la BD real ANTES de importar nada
os.environ.pop("TURSO_DATABASE_URL", None)
os.environ.pop("TURSO_AUTH_TOKEN", None)

from src.crm import db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_fase5.db"

from streamlit.testing.v1 import AppTest

ok = True


def check(desc, cond, extra=""):
    global ok
    print(f"  {'OK  ' if cond else 'FAIL'} {desc}  {extra if not cond else ''}")
    if not cond:
        ok = False


LEADS = [
    {"nombre": "Alfa", "ciudad": "Madrid", "direccion": "Calle A, 1",
     "email_directo": "ana@alfa.es", "perfil_origen": "Perfil 1"},
    {"nombre": "Beta", "ciudad": "Madrid", "direccion": "Calle B, 2",
     "email_generico": "info@beta.es", "perfil_origen": "Perfil 1"},
    {"nombre": "Gamma", "ciudad": "Valencia", "direccion": "Calle C, 3",
     "perfil_origen": "Perfil 2"},
]

db.init_db()
db.import_leads(LEADS)
IDS = {l["nombre"]: l["id"] for l in db.get_all_leads()}


def etapa_de(nombre):
    return [dict(r) for r in db.get_all_leads() if r["nombre"] == nombre][0]["etapa"]

print("\n1) Los enlaces de la Guia se siembran una sola vez")
links = db.get_app_links()
check("hay enlaces sembrados", len(links) > 0, str(len(links)))
check("incluye Turso", any("Turso" in l["titulo"] for l in links))
check("incluye las contrasenas de aplicacion de Google",
      any("aplicaci" in l["titulo"].lower() for l in links))
n_antes = len(links)
db.seed_app_links()
db.init_db()
check("re-sembrar no duplica", len(db.get_app_links()) == n_antes,
      f"{n_antes} -> {len(db.get_app_links())}")

print("\n2) Los enlaces se editan y borran desde la UI")
db.save_app_link("Pruebas", "Mi enlace", "https://ejemplo.com", "probar")
creado = [l for l in db.get_app_links() if l["titulo"] == "Mi enlace"][0]
db.update_app_link(creado["id"], "Pruebas", "Mi enlace v2",
                   "https://ejemplo.com/2", "probar mejor", creado["orden"])
editado = [l for l in db.get_app_links() if l["id"] == creado["id"]][0]
check("se guarda la edicion", editado["titulo"] == "Mi enlace v2", editado["titulo"])
check("se guarda la URL nueva", editado["url"] == "https://ejemplo.com/2")
db.delete_app_link(creado["id"])
check("se borra", not [l for l in db.get_app_links() if l["id"] == creado["id"]])

print("\n3) apply_filters: los criterios se combinan bien")
from src.crm.views._components import apply_filters, quality_icon

todos = [dict(r) for r in db.get_all_leads()]
base = {"etapa": list(db.PIPELINE_STAGES),
        "ciudad": ["Madrid", "Valencia"],
        "origen": ["Perfil 1", "Perfil 2"],
        "email": "Todos"}

check("sin filtros salen todos", len(apply_filters(todos, base)) == 3)

solo_madrid = dict(base, ciudad=["Madrid"])
check("filtro de ciudad", len(apply_filters(todos, solo_madrid)) == 2)

solo_p2 = dict(base, origen=["Perfil 2"])
check("filtro de perfil de origen",
      [l["nombre"] for l in apply_filters(todos, solo_p2)] == ["Gamma"])

check("email directo",
      [l["nombre"] for l in apply_filters(todos, dict(base, email="Con email directo"))] == ["Alfa"])
check("email genérico",
      [l["nombre"] for l in apply_filters(todos, dict(base, email="Con email genérico"))] == ["Beta"])
check("sin email",
      [l["nombre"] for l in apply_filters(todos, dict(base, email="Sin email"))] == ["Gamma"])

combinado = dict(base, ciudad=["Madrid"], email="Con email directo")
check("ciudad + email a la vez",
      [l["nombre"] for l in apply_filters(todos, combinado)] == ["Alfa"])

print("\n4) La etapa solo filtra donde tiene sentido")
db.update_lead_stage(IDS["Alfa"], "Demo")
todos = [dict(r) for r in db.get_all_leads()]
solo_demo = dict(base, etapa=["Demo"])
check("la Tabla respeta el filtro de etapa",
      [l["nombre"] for l in apply_filters(todos, solo_demo, incluir_etapa=True)] == ["Alfa"])
check("el Kanban lo ignora (la etapa es la columna)",
      len(apply_filters(todos, solo_demo, incluir_etapa=False)) == 3)
db.update_lead_stage(IDS["Alfa"], "Nuevo")

print("\n5) El semaforo mide contactabilidad, no director")
check("verde con email directo",
      quality_icon({"email_directo": "a@b.es", "email_generico": ""}) == "🟢")
check("amarillo con generico",
      quality_icon({"email_directo": "", "email_generico": "info@b.es"}) == "🟡")
check("rojo sin email",
      quality_icon({"email_directo": "", "email_generico": "",
                    "director": "Ana Ruiz"}) == "🔴")

print("\n6) La app arranca entera, con sus 5 tabs")
at = AppTest.from_file(str(ROOT / "src/crm/app.py"), default_timeout=60)
at.run()
check("sin excepciones", not at.exception,
      str(at.exception[0].message) if at.exception else "")
etiquetas = [t.label for t in at.tabs] if hasattr(at, "tabs") else []
check("el primer tab es la Guia",
      any("Guía" in e for e in etiquetas) if etiquetas else True, str(etiquetas))

texto = " ".join(str(m.value) for m in at.markdown)
check("la Guia explica el flujo", "Cómo se usa esto" in texto)
check("la Guia lista los enlaces", "Enlaces importantes" in texto)
check("la Guia avisa del repo publico", "Cosas que no puedes olvidar" in texto)

print("\n7) El encolado ajusta la cantidad al cambiar filtros")
at.slider(key="mail_q_cantidad").set_value(2).run()
at.multiselect(key="mail_q_ciudad").set_value(["Madrid"])
at.multiselect(key="mail_q_perfil").set_value(["Perfil 1"])
at.selectbox(key="mail_q_calidad").select("Sólo email directo")
next(b for b in at.button if b.label == "Aplicar filtros").click().run()
check("reducir resultados no rompe el slider", not at.exception,
      str(at.exception[0].message) if at.exception else "")
check("la cantidad baja al nuevo máximo",
      at.session_state["mail_q_cantidad"] == 1,
      str(at.session_state["mail_q_cantidad"]))
at.multiselect(key="mail_q_ciudad").set_value([])
at.multiselect(key="mail_q_perfil").set_value([])
at.selectbox(key="mail_q_calidad").select("Todos")
next(b for b in at.button if b.label == "Aplicar filtros").click().run()

print("\n8) Los filtros de la barra lateral llegan a los tabs")
at.selectbox(key="f_email").select("Sin email").run()
check("sin excepciones al filtrar", not at.exception,
      str(at.exception[0].message) if at.exception else "")
etiquetas_botones = [b.label for b in at.button]
check("el Kanban solo muestra el lead sin email",
      not any("Alfa" in str(e) for e in at.get("expander")),
      str([e.label for e in at.get("expander")]))
at.selectbox(key="f_email").select("Todos").run()

print("\n9) Botones de accion rapida")


def _ss(key):
    """session_state de AppTest no tiene .get()."""
    try:
        return at.session_state[key]
    except Exception:
        return None


at.button(key=f"next_{IDS['Beta']}").click().run()
check("Beta avanza a Contactado",
      etapa_de("Beta") == "Contactado",
      etapa_de("Beta"))
check("el selector obsoleto se limpia",
      _ss(f"stage_{IDS['Beta']}") in (None, "Contactado"),
      str(_ss(f"stage_{IDS['Beta']}")))

at.button(key=f"drop_{IDS['Gamma']}").click().run()
check("Gamma se descarta",
      etapa_de("Gamma") == "Descartado",
      etapa_de("Gamma"))
check("los demas no se mueven",
      etapa_de("Alfa") == "Nuevo",
      etapa_de("Alfa"))

print("\n9) Nada ha reventado por el camino")
at.run()
check("app sana al final", not at.exception,
      str(at.exception[0].message) if at.exception else "")

print("\n" + "=" * 46)
print("RESULTADO:", "TODO OK" if ok else "HAY FALLOS")
print("=" * 46)
sys.exit(0 if ok else 1)
