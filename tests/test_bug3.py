"""
Test de BUG-3 — criterio de deduplicacion unico entre scraper y BD.

Uso:  python tests/test_bug3.py

Crea una BD SQLite temporal. No toca tu BD local ni Turso.
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
from src.models.lead import Lead, make_dedup_key, clean_text  # noqa: E402

db.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"

ok = True


def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"  OK   {label}")
    else:
        ok = False
        print(f"  FAIL {label}  {detail}")


def fresh_db():
    """BD limpia para cada bloque."""
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
    db.init_db()


SEDE_A = "C. de Marcelo Usera, 43, Usera, 28026 Madrid"
SEDE_B = "Calle de Maria de Molina, 18, Salamanca, 28006 Madrid"

print("\n1) El caso real del bug: cadena con 2 sedes en la misma ciudad")
fresh_db()
insertados = db.import_leads([
    {"nombre": "Clinicas Origen", "ciudad": "Madrid", "direccion": SEDE_A},
    {"nombre": "Clinicas Origen", "ciudad": "Madrid", "direccion": SEDE_B},
])
check("entran las 2 sedes (antes se perdia 1)", insertados == 2, f"entraron {insertados}")

print("\n2) El duplicado real sigue detectandose")
fresh_db()
insertados = db.import_leads([
    {"nombre": "Clinica Unica", "ciudad": "Madrid", "direccion": SEDE_A},
    {"nombre": "Clinica Unica", "ciudad": "Madrid", "direccion": SEDE_A},
])
check("misma direccion -> 1 sola fila", insertados == 1, f"entraron {insertados}")

print("\n3) Scraper y BD usan exactamente la misma clave")
lead = Lead(nombre="Clinica X", ciudad="Madrid", direccion=SEDE_A)
check("Lead.dedup_key == make_dedup_key()",
      lead.dedup_key == make_dedup_key("Clinica X", "Madrid", SEDE_A),
      lead.dedup_key)

print("\n4) Basura de Google Maps en la direccion no rompe la clave")
sucia = "\ue0c8\n" + SEDE_A          # glifo de icono + salto de linea reales
check("glifo privado + salto se ignoran",
      make_dedup_key("Clinica X", "Madrid", sucia)
      == make_dedup_key("Clinica X", "Madrid", SEDE_A))
check("mayusculas y espacios dobles se ignoran",
      make_dedup_key("  CLINICA   x ", "Madrid", SEDE_A.upper())
      == make_dedup_key("Clinica X", "Madrid", SEDE_A))
check("clean_text limpia para mostrar", clean_text(sucia) == SEDE_A, repr(clean_text(sucia)))

fresh_db()
insertados = db.import_leads([
    {"nombre": "Clinica X", "ciudad": "Madrid", "direccion": sucia},
    {"nombre": "clinica x", "ciudad": "Madrid", "direccion": SEDE_A},
])
check("la BD tampoco los duplica", insertados == 1, f"entraron {insertados}")
conn = db.get_conn()
guardada = conn.execute("SELECT direccion FROM leads").fetchone()["direccion"]
conn.close()
check("la direccion se guarda ya limpia", guardada == SEDE_A, repr(guardada))

print("\n5) Sin direccion se recurre a nombre + ciudad (no colapsan entre ciudades)")
fresh_db()
insertados = db.import_leads([
    {"nombre": "Psicologo Juan Perez", "ciudad": "Madrid", "direccion": ""},
    {"nombre": "Psicologo Juan Perez", "ciudad": "Malaga", "direccion": ""},
    {"nombre": "Psicologo Juan Perez", "ciudad": "Madrid", "direccion": ""},
])
check("2 ciudades distintas entran, el repetido no", insertados == 2, f"entraron {insertados}")

print("\n6) Duplicados dentro del mismo lote")
fresh_db()
insertados = db.import_leads([
    {"nombre": "Clinica Y", "ciudad": "Madrid", "direccion": SEDE_A},
    {"nombre": "Clinica Y", "ciudad": "Madrid", "direccion": SEDE_A},
    {"nombre": "Clinica Y", "ciudad": "Madrid", "direccion": SEDE_A},
])
check("3 iguales en un lote -> 1 fila", insertados == 1, f"entraron {insertados}")

print("\n7) Leads sin nombre se descartan")
fresh_db()
insertados = db.import_leads([
    {"nombre": "", "ciudad": "Madrid", "direccion": SEDE_A},
    {"nombre": "   ", "ciudad": "Madrid", "direccion": SEDE_B},
    {"nombre": "Clinica Valida", "ciudad": "Madrid", "direccion": SEDE_A},
])
check("solo entra la valida", insertados == 1, f"entraron {insertados}")

print("\n8) El indice UNIQUE impide duplicados aunque se inserte a mano")
fresh_db()
db.import_leads([{"nombre": "Clinica Z", "ciudad": "Madrid", "direccion": SEDE_A}])
conn = db.get_conn()
key = conn.execute("SELECT dedup_key FROM leads").fetchone()["dedup_key"]
try:
    conn.execute(
        "INSERT INTO leads (nombre, ciudad, direccion, dedup_key) VALUES (?,?,?,?)",
        ("Clinica Z", "Madrid", SEDE_A, key),
    )
    conn.commit()
    check("la BD deberia rechazar el duplicado", False)
except Exception as e:
    check(f"rechazado por la BD ({type(e).__name__})", True)
conn.close()

print("\n9) Migracion de una BD antigua: backfill + colapso de duplicados")
fresh_db()
conn = db.get_conn()
# Simulamos filas heredadas: sin dedup_key y con un duplicado real.
# La fila rica (notas + etapa avanzada) debe sobrevivir al colapso.
conn.executemany(
    "INSERT INTO leads (nombre, ciudad, direccion, dedup_key, notas, etapa, email_directo) "
    "VALUES (?,?,?,'',?,?,?)",
    [
        ("Clinica Vieja", "Madrid", SEDE_A, "", "Nuevo", ""),
        ("Clinica Vieja", "Madrid", SEDE_A, "Llamada el martes", "Demo", "a@b.com"),
        ("Clinica Sola", "Madrid", SEDE_B, "", "Nuevo", ""),
    ],
)
conn.commit()
conn.close()

resumen = db.backfill_dedup_keys()
check("elimina 1 duplicado", resumen["duplicados"] == 1, str(resumen))
check("calcula 2 claves (la borrada ya no la necesita)",
      resumen["claves"] == 2, str(resumen))

conn = db.get_conn()
filas = [dict(r) for r in conn.execute("SELECT nombre, notas, etapa FROM leads")]
conn.close()
check("quedan 2 filas", len(filas) == 2, str(len(filas)))
superviviente = [f for f in filas if f["nombre"] == "Clinica Vieja"]
check("sobrevive la fila con notas y etapa avanzada",
      len(superviviente) == 1
      and superviviente[0]["notas"] == "Llamada el martes"
      and superviviente[0]["etapa"] == "Demo",
      str(superviviente))
check("es idempotente (2a pasada no toca nada)",
      db.backfill_dedup_keys() == {"claves": 0, "duplicados": 0})

print("\n9b) Insercion manual sin dedup_key: se tolera y se repara sola")
conn = db.get_conn()
conn.executemany(
    "INSERT INTO leads (nombre, ciudad, direccion, dedup_key) VALUES (?,?,?,'')",
    [("Manual Uno", "Sevilla", "Calle A, 1"), ("Manual Dos", "Sevilla", "Calle B, 2")],
)
conn.commit()
conn.close()
check("el indice parcial no bloquea 2 filas con clave vacia", True)
resumen = db.backfill_dedup_keys()
check("el backfill les calcula la clave", resumen["claves"] == 2, str(resumen))
check("y no las borra por error", resumen["duplicados"] == 0, str(resumen))

print("\n10) Datos reales del proyecto")
real = ROOT / "data" / "leads_enriched.json"
if real.exists():
    import json
    leads = json.load(open(real, encoding="utf-8"))
    fresh_db()
    insertados = db.import_leads(leads)
    conn = db.get_conn()
    total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    conn.close()
    print(f"     {len(leads)} leads en el JSON -> {insertados} importados")
    check("no se pierde ningun lead legitimo", insertados == 311, f"importados {insertados}")
    check("sin duplicados en BD", total == insertados)
    print("     (con la clave antigua nombre+ciudad se perdian 3)")
else:
    print("     (omitido: no existe data/leads_enriched.json)")

print("\n" + "=" * 46)
print("RESULTADO:", "TODO OK" if ok else "HAY FALLOS")
print("=" * 46)
sys.exit(0 if ok else 1)
