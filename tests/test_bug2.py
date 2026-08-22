"""
Test de BUG-2 — una etapa invalida no debe tumbar la app.

Uso:  python tests/test_bug2.py

Crea una BD SQLite temporal. No toca tu BD local ni Turso.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# BD temporal aislada, y aseguramos que NO se use Turso
os.environ.pop("TURSO_DATABASE_URL", None)
os.environ.pop("TURSO_AUTH_TOKEN", None)

from src.crm import db  # noqa: E402

db.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"

ok = True


def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"  OK   {label}")
    else:
        ok = False
        print(f"  FAIL {label}  {detail}")


print("\n1) Se reproduce el crash original")
try:
    db.PIPELINE_STAGES.index("Scraped")
    check("PIPELINE_STAGES.index('Scraped') deberia petar", False)
except ValueError as e:
    print(f"  OK   Reproducido: ValueError -> {e}")

print("\n2) normalize_stage() traduce cualquier valor a una etapa valida")
casos = [
    ("Scraped", "Nuevo"),
    ("Enriched", "Nuevo"),
    ("contacted", "Contactado"),
    ("", "Nuevo"),
    (None, "Nuevo"),
    ("  nuevo  ", "Nuevo"),
    ("CONTACTADO", "Contactado"),
    ("etapa_inventada", "Nuevo"),
    ("Demo", "Demo"),
]
for entrada, esperado in casos:
    got = db.normalize_stage(entrada)
    check(f"{entrada!r:>18} -> {got}", got == esperado, f"(esperaba {esperado})")

print("\n3) stage_index() nunca lanza ValueError")
for entrada, _ in casos:
    try:
        idx = db.stage_index(entrada)
        check(f"{entrada!r:>18} -> indice {idx}", 0 <= idx < len(db.PIPELINE_STAGES))
    except Exception as e:
        check(f"{entrada!r:>18}", False, f"lanzo {type(e).__name__}: {e}")

print("\n4) Filas corruptas en BD se auto-reparan")
db.init_db()
conn = db.get_conn()
conn.executemany(
    "INSERT INTO leads (nombre, ciudad, etapa) VALUES (?, ?, ?)",
    [
        ("Clinica Corrupta", "Madrid", "Scraped"),
        ("Clinica Vacia", "Madrid", ""),
        ("Clinica Rara", "Madrid", "loquesea"),
        ("Clinica Sana", "Madrid", "Demo"),
    ],
)
conn.execute(
    "INSERT INTO leads (nombre, ciudad, etapa) VALUES (?, ?, NULL)",
    ("Clinica Nula", "Madrid"),
)
conn.commit()
conn.close()

reparadas = db.repair_invalid_stages()
check("repara 4 filas (Scraped, vacia, rara, NULL)", reparadas == 4, f"reparo {reparadas}")

conn = db.get_conn()
rows = {r["nombre"]: r["etapa"] for r in conn.execute("SELECT nombre, etapa FROM leads")}
conn.close()
check("'Scraped' -> Nuevo", rows["Clinica Corrupta"] == "Nuevo", rows["Clinica Corrupta"])
check("'' -> Nuevo", rows["Clinica Vacia"] == "Nuevo", rows["Clinica Vacia"])
check("'loquesea' -> Nuevo", rows["Clinica Rara"] == "Nuevo", rows["Clinica Rara"])
check("NULL -> Nuevo", rows["Clinica Nula"] == "Nuevo", rows["Clinica Nula"])
check("'Demo' NO se toca", rows["Clinica Sana"] == "Demo", rows["Clinica Sana"])
check("es idempotente (2a pasada no escribe)", db.repair_invalid_stages() == 0)

print("\n5) Toda la BD es ya indexable: la app no puede caer")
conn = db.get_conn()
etapas = [r["etapa"] for r in conn.execute("SELECT etapa FROM leads")]
conn.close()
crash = [e for e in etapas if e not in db.PIPELINE_STAGES]
check(f"{len(etapas)} etapas verificadas con .index() directo", not crash, str(crash))

print("\n6) import_leads respeta etapas validas y sanea las invalidas")
db.import_leads([
    {"nombre": "Import Valida", "ciudad": "Valencia", "etapa": "Cerrado"},
    {"nombre": "Import Rara", "ciudad": "Valencia", "etapa": "Scraped"},
    {"nombre": "Import Sin Etapa", "ciudad": "Valencia"},
])
conn = db.get_conn()
rows = {r["nombre"]: r["etapa"] for r in conn.execute("SELECT nombre, etapa FROM leads")}
conn.close()
check("etapa valida se conserva (util al restaurar backup)",
      rows["Import Valida"] == "Cerrado", rows["Import Valida"])
check("etapa invalida -> Nuevo", rows["Import Rara"] == "Nuevo", rows["Import Rara"])
check("sin etapa -> Nuevo", rows["Import Sin Etapa"] == "Nuevo", rows["Import Sin Etapa"])

print("\n7) update_lead_stage no puede meter basura en BD")
conn = db.get_conn()
lead_id = conn.execute("SELECT id FROM leads LIMIT 1").fetchone()["id"]
conn.close()
db.update_lead_stage(lead_id, "EtapaFalsa")
conn = db.get_conn()
etapa = conn.execute(
    "SELECT etapa FROM leads WHERE id = ?", (lead_id,)
).fetchone()["etapa"]
conn.close()
check("'EtapaFalsa' se guarda como 'Nuevo'", etapa == "Nuevo", etapa)

print("\n" + "=" * 46)
print("RESULTADO:", "TODO OK" if ok else "HAY FALLOS")
print("=" * 46)
sys.exit(0 if ok else 1)
