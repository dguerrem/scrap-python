"""
Test de BUG-4 — las notas no deben escribirse en BD en cada rerun.

Uso:  python tests/test_bug4.py

Levanta la app real con streamlit.testing (AppTest) sobre una BD SQLite
temporal y cuenta las escrituras. No toca tu BD local ni Turso.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.pop("TURSO_DATABASE_URL", None)
os.environ.pop("TURSO_AUTH_TOKEN", None)

from src.crm import db  # noqa: E402

db.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
db.init_db()
db.import_leads([
    {"nombre": "Clinica Alfa", "ciudad": "Madrid", "direccion": "Calle A, 1"},
    {"nombre": "Clinica Beta", "ciudad": "Madrid", "direccion": "Calle B, 2"},
])

conn = db.get_conn()
IDS = {r["nombre"]: r["id"] for r in conn.execute("SELECT id, nombre FROM leads")}
conn.close()
ID_A, ID_B = IDS["Clinica Alfa"], IDS["Clinica Beta"]

# --- Contadores de escritura -------------------------------------------------
ESCRITURAS = {"notas": [], "etapa": []}
_real_notes, _real_stage = db.update_lead_notes, db.update_lead_stage


def _spy_notes(lead_id, notas):
    ESCRITURAS["notas"].append((lead_id, notas))
    return _real_notes(lead_id, notas)


def _spy_stage(lead_id, etapa):
    ESCRITURAS["etapa"].append((lead_id, etapa))
    return _real_stage(lead_id, etapa)


db.update_lead_notes = _spy_notes
db.update_lead_stage = _spy_stage

from streamlit.testing.v1 import AppTest  # noqa: E402

ok = True


def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"  OK   {label}")
    else:
        ok = False
        print(f"  FAIL {label}  {detail}")


def notas_en_bd(lead_id):
    conn = db.get_conn()
    row = conn.execute("SELECT notas FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    return row["notas"] or ""


def etapa_en_bd(lead_id):
    conn = db.get_conn()
    row = conn.execute("SELECT etapa FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    return row["etapa"]


at = AppTest.from_file(str(ROOT / "src" / "crm" / "app.py"), default_timeout=90)
at.run()
check("la app arranca sin excepciones", not at.exception, str(at.exception))

print("\n1) Escribir una nota provoca UNA sola escritura")
ESCRITURAS["notas"].clear()
at.text_area(key=f"detail_notas_{ID_A}").set_value("Llamada el martes").run()
check("1 UPDATE tras editar", len(ESCRITURAS["notas"]) == 1, str(ESCRITURAS["notas"]))
check("el texto llega a BD", notas_en_bd(ID_A) == "Llamada el martes", notas_en_bd(ID_A))

print("\n2) Los reruns posteriores NO vuelven a escribir (el bug)")
for i in range(5):
    at.run()
check("sigue habiendo 1 sola escritura tras 5 reruns",
      len(ESCRITURAS["notas"]) == 1,
      f"hubo {len(ESCRITURAS['notas'])} (antes del fix: 1 por rerun)")

print("\n3) Interactuar con otro widget tampoco reescribe las notas")
ESCRITURAS["notas"].clear()
# La etiqueta del selector lleva el semaforo delante desde la Fase 5, asi que
# se busca la opcion por el nombre en vez de escribirla entera.
_opt_beta = next(o for o in at.selectbox(key="detail_lead").options
                 if "Clinica Beta" in o)
at.selectbox(key="detail_lead").select(_opt_beta).run()
at.run()
check("0 escrituras al cambiar de lead", len(ESCRITURAS["notas"]) == 0,
      str(ESCRITURAS["notas"]))

print("\n4) Cambiar de lead no contamina al siguiente")
# Con la clave fija anterior ("detail_notas"), Streamlit conservaba el texto
# del lead A y lo guardaba sobre el lead B al cambiar de seleccion.
check("el recuadro de Beta esta vacio, no muestra la nota de Alfa",
      at.text_area(key=f"detail_notas_{ID_B}").value == "",
      repr(at.text_area(key=f"detail_notas_{ID_B}").value))
check("Beta sigue sin notas en BD", notas_en_bd(ID_B) == "", repr(notas_en_bd(ID_B)))
check("Alfa conserva las suyas", notas_en_bd(ID_A) == "Llamada el martes")

print("\n5) La nota de cada lead se guarda en su propia fila")
ESCRITURAS["notas"].clear()
at.text_area(key=f"detail_notas_{ID_B}").set_value("Interesados en demo").run()
check("1 escritura", len(ESCRITURAS["notas"]) == 1, str(ESCRITURAS["notas"]))
check("va al lead correcto", ESCRITURAS["notas"][0][0] == ID_B, str(ESCRITURAS["notas"]))
check("Beta tiene su nota", notas_en_bd(ID_B) == "Interesados en demo")
check("Alfa no se ha tocado", notas_en_bd(ID_A) == "Llamada el martes")

print("\n6) Cambiar de etapa: una escritura, al lead correcto")
ESCRITURAS["etapa"].clear()
at.selectbox(key=f"detail_stage_{ID_B}").select("Demo").run()
check("1 UPDATE de etapa", len(ESCRITURAS["etapa"]) == 1, str(ESCRITURAS["etapa"]))
check("Beta pasa a Demo", etapa_en_bd(ID_B) == "Demo", etapa_en_bd(ID_B))
check("Alfa sigue en Nuevo", etapa_en_bd(ID_A) == "Nuevo", etapa_en_bd(ID_A))
for i in range(3):
    at.run()
check("3 reruns no reescriben la etapa", len(ESCRITURAS["etapa"]) == 1,
      str(ESCRITURAS["etapa"]))

print("\n7) El Kanban se comporta igual")
ESCRITURAS["notas"].clear()
at.text_area(key=f"notas_{ID_A}").set_value("Nota desde el Kanban").run()
check("1 escritura", len(ESCRITURAS["notas"]) == 1, str(ESCRITURAS["notas"]))
check("guardada en Alfa", notas_en_bd(ID_A) == "Nota desde el Kanban", notas_en_bd(ID_A))
for i in range(3):
    at.run()
check("3 reruns no reescriben", len(ESCRITURAS["notas"]) == 1, str(ESCRITURAS["notas"]))

print("\n8) Sin excepciones en toda la sesion")
check("app sana al final", not at.exception, str(at.exception))

print("\n" + "=" * 46)
print("RESULTADO:", "TODO OK" if ok else "HAY FALLOS")
print("=" * 46)
sys.exit(0 if ok else 1)
