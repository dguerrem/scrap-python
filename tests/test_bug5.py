"""
BUG-5 — el codigo de db.py reventaba en Turso pero no en SQLite local.

    ERROR importando a Turso: TypeError: '_Cursor' object is not iterable

Causa: `for r in conn.execute(...)` funciona con sqlite3 (su cursor es
iterable) pero el cursor de la capa HTTP de Turso no lo era. El fallo solo
aparecia en cloud, con los datos ya scrapeados.

Este test ejecuta el codigo real de db.py contra una conexion que habla
exactamente igual que TursoConnection (mismos objetos Row y _Cursor, commit
que no hace nada) pero guarda en un SQLite temporal. Asi cualquier uso de una
caracteristica que solo existe en sqlite3 explota aqui, en local, y no en
produccion.

Ejecutar:  python tests/test_bug5.py
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.pop("TURSO_DATABASE_URL", None)
os.environ.pop("TURSO_AUTH_TOKEN", None)

from src.crm import db
from src.crm import turso_http

db.DB_PATH = Path(tempfile.mkdtemp()) / "no_deberia_usarse.db"

ok = True


def check(desc, cond, extra=""):
    global ok
    print(f"  {'OK  ' if cond else 'FAIL'} {desc}  {extra if not cond else ''}")
    if not cond:
        ok = False


# ======================================================
# Doble de Turso: misma superficie de API, datos en local
# ======================================================

class FakeTursoConn:
    """Se comporta como TursoConnection, no como sqlite3.Connection.

    Devuelve los _Cursor y Row de verdad de turso_http, y su commit() y
    close() no hacen nada (Turso confirma cada sentencia por su cuenta).
    """

    def __init__(self, path):
        # isolation_level=None = autocommit, como el endpoint HTTP de Turso
        self._db = sqlite3.connect(str(path), isolation_level=None)
        self.row_factory = None
        self.sentencias = []

    def execute(self, sql, params=()):
        self.sentencias.append(sql.strip().split()[0].upper())
        cur = self._db.execute(sql, tuple(params))
        cols = [d[0] for d in cur.description] if cur.description else []
        filas = cur.fetchall() if cur.description else []
        rows = [
            turso_http.Row(cols, list(v)) if self.row_factory else tuple(v)
            for v in filas
        ]
        return turso_http._Cursor(rows)

    def executemany(self, sql, seq_of_params):
        self._db.executemany(sql, [tuple(p) for p in seq_of_params])
        return turso_http._Cursor([])

    def commit(self):
        pass

    def close(self):
        pass


FAKE_PATH = Path(tempfile.mkdtemp()) / "fake_turso.db"
FAKE = FakeTursoConn(FAKE_PATH)


def _fake_get_conn():
    # get_conn() de verdad asigna row_factory tras construir la conexion;
    # el doble tiene que hacer exactamente lo mismo o las filas llegarian
    # como tuplas y el test mentiria.
    FAKE.row_factory = sqlite3.Row
    return FAKE


db.get_conn = _fake_get_conn


LEADS = [
    {"nombre": "Clinica Uno", "ciudad": "Murcia", "direccion": "Calle A, 1",
     "email_directo": "ana@uno.es", "puntuacion": 4.9, "resenas": 150},
    {"nombre": "Clinica Dos", "ciudad": "Murcia", "direccion": "Calle B, 2",
     "email_generico": "info@dos.es", "puntuacion": 4.6, "resenas": 157},
    {"nombre": "Clinica Tres", "ciudad": "Murcia", "direccion": "Calle C, 3"},
]


print("\n1) El cursor de Turso ya se puede recorrer con for")
cur = turso_http._Cursor([turso_http.Row(["a"], [1]), turso_http.Row(["a"], [2])])
try:
    valores = [r["a"] for r in cur]
    check("iterar un _Cursor no lanza TypeError", valores == [1, 2], str(valores))
except TypeError as e:
    check("iterar un _Cursor no lanza TypeError", False, str(e))
check("len() sobre el cursor", len(cur) == 2)
check("fetchall sigue funcionando", len(cur.fetchall()) == 2)
check("fetchone sigue funcionando", cur.fetchone()["a"] == 1)

print("\n2) init_db() completo contra una conexion tipo Turso")
try:
    db.init_db()
    check("crea el esquema sin usar nada exclusivo de sqlite3", True)
except Exception as e:
    check("init_db funciona en cloud", False, f"{type(e).__name__}: {e}")

print("\n3) El import que fallo en produccion")
# Es la misma llamada que hace el workflow: import_from_json -> import_leads
try:
    n = db.import_leads(LEADS, perfil_origen="Murcia test")
    check("import_leads no lanza TypeError", True)
    check("entran los 3 leads", n == 3, str(n))
except TypeError as e:
    check("import_leads no lanza TypeError", False, str(e))
except Exception as e:
    check("import_leads funciona en cloud", False, f"{type(e).__name__}: {e}")

print("\n4) La deduplicacion sigue funcionando en cloud")
n2 = db.import_leads(LEADS, perfil_origen="Murcia test")
check("reimportar lo mismo no duplica", n2 == 0, str(n2))
check("siguen siendo 3", len(db.get_all_leads()) == 3, str(len(db.get_all_leads())))

print("\n5) Con el fichero real del scraper")
enriched = ROOT / "data" / "leads_enriched.json"
if enriched.exists():
    try:
        antes = len(db.get_all_leads())
        n3 = db.import_from_json(enriched, perfil_origen="Fichero real")
        check("import_from_json contra Turso", True)
        check("importa leads del JSON real", n3 > 0, str(n3))
        check("el total cuadra", len(db.get_all_leads()) == antes + n3)
    except Exception as e:
        check("import_from_json contra Turso", False, f"{type(e).__name__}: {e}")
else:
    print("  --   (sin data/leads_enriched.json, se salta)")

print("\n6) El resto de operaciones del CRM tampoco usan atajos de sqlite3")
lead_id = db.get_all_leads()[0]["id"]
pruebas = [
    ("get_all_leads", lambda: db.get_all_leads()),
    ("get_leads_by_stage", lambda: db.get_leads_by_stage("Nuevo")),
    ("get_stats", lambda: db.get_stats()),
    ("update_lead_stage", lambda: db.update_lead_stage(lead_id, "Contactado")),
    ("update_lead_notes", lambda: db.update_lead_notes(lead_id, "nota cloud")),
    ("get_leads_to_enrich", lambda: db.get_leads_to_enrich(5)),
    ("repair_invalid_stages", lambda: db.repair_invalid_stages()),
    ("backfill_dedup_keys", lambda: db.backfill_dedup_keys()),
    ("seed_app_links", lambda: db.seed_app_links()),
    ("get_app_links", lambda: db.get_app_links()),
    ("save_app_link", lambda: db.save_app_link("Test", "T", "https://t.es", "x")),
    ("save_scrap_profile", lambda: db.save_scrap_profile(
        "Perfil cloud", "Clinica en {city}", ["Murcia"], 20, 4.0, "required", 5, 1)),
    ("get_scrap_profiles", lambda: db.get_scrap_profiles()),
]
for nombre, fn in pruebas:
    try:
        fn()
        check(nombre, True)
    except Exception as e:
        check(nombre, False, f"{type(e).__name__}: {e}")

print("\n7) Los datos escritos se leen de vuelta")
lead = [l for l in db.get_all_leads() if l["id"] == lead_id][0]
check("la etapa se guardo", lead["etapa"] == "Contactado", lead["etapa"])
check("la nota se guardo", lead["notas"] == "nota cloud", repr(lead["notas"]))
perfiles = db.get_scrap_profiles()
check("el perfil se guardo", any(p["nombre"] == "Perfil cloud" for p in perfiles))
check("las ciudades se deserializan",
      perfiles[0]["ciudades"] == ["Murcia"], str(perfiles[0]["ciudades"]))

print("\n8) El mailer tampoco usa atajos de sqlite3 (Fase 6)")
# El motor de envio corre en GitHub Actions contra Turso, asi que su capa de
# datos pasa por el mismo doble. Lo critico es el claim atomico: sin
# transacciones, si esa sentencia no funciona igual en cloud se enviarian
# correos duplicados.
os.environ["EMAIL_DRY_RUN"] = "1"
from src.mailer import store as mstore

pruebas_mailer = [
    ("set_setting", lambda: mstore.set_setting("tope_manual", "7")),
    ("get_setting", lambda: mstore.get_setting("tope_manual")),
    ("all_settings", lambda: mstore.all_settings()),
    ("registrar_ledger", lambda: mstore.registrar_ledger("cloud.es", "a@cloud.es", 1)),
    ("en_ledger", lambda: mstore.en_ledger("cloud.es")),
    ("suprimir", lambda: mstore.suprimir("vetado.es", "x@vetado.es", "test")),
    ("listar_supresion", lambda: mstore.listar_supresion()),
    ("encolar", lambda: mstore.encolar(1, "hola@encolado.es", "a", "b", "c")),
    ("claim", lambda: mstore.claim()),
    ("contar_cola", lambda: mstore.contar_cola()),
    ("liberar_atascados", lambda: mstore.liberar_atascados()),
    ("log", lambda: mstore.log("test", "detalle")),
    ("ultimos_logs", lambda: mstore.ultimos_logs(5)),
    ("historial", lambda: mstore.historial(5)),
    ("ultimo_envio", lambda: mstore.ultimo_envio()),
    ("guardar_plantilla", lambda: mstore.guardar_plantilla("P", "A {nombre}", "C")),
    ("plantillas", lambda: mstore.plantillas()),
    ("reintentar_fallidos", lambda: mstore.reintentar_fallidos()),
]
for nombre, fn in pruebas_mailer:
    try:
        fn()
        check(nombre, True)
    except Exception as e:
        check(nombre, False, f"{type(e).__name__}: {e}")

check("el ajuste se lee de vuelta", mstore.get_setting("tope_manual") == "7",
      mstore.get_setting("tope_manual"))
check("el ledger reserva el dominio", mstore.en_ledger("cloud.es"))
check("un dominio ya en ledger no se puede reservar dos veces",
      mstore.registrar_ledger("cloud.es", "b@cloud.es", 2) is False)
check("un dominio suprimido no se encola",
      mstore.encolar(2, "x@vetado.es", "a", "b", "c") is False)

# El claim ya vacio la cola en el bucle anterior: se reencola con dos dominios
# DISTINTOS para probar que dos claims consecutivos nunca devuelven la misma fila.
mstore.encolar(3, "hola@carrera-uno.es", "a", "b", "c")
mstore.encolar(4, "hola@carrera-dos.es", "a", "b", "c")
primero, segundo = mstore.claim(), mstore.claim()
check("el claim atomico funciona igual en cloud",
      primero and segundo and primero["id"] != segundo["id"],
      f"{primero and primero['id']} vs {segundo and segundo['id']}")
check("con la cola vacia el claim no devuelve nada", mstore.claim() is None)
check("dos buzones del mismo dominio no se encolan dos veces",
      mstore.encolar(5, "uno@misma-casa.es", "a", "b", "c") is True
      and mstore.encolar(6, "dos@misma-casa.es", "a", "b", "c") is False)

from src.mailer import autonomy as mautonomy
try:
    datos = mautonomy.resumen()
    check("el panel de autonomia se calcula en cloud", isinstance(datos["contactables"], int))
except Exception as e:
    check("el panel de autonomia se calcula en cloud", False, f"{type(e).__name__}: {e}")

print("\n9) Ningun sitio de db.py recorre un cursor sin fetchall")
# Red de seguridad por si vuelve el patron en codigo nuevo: aunque ahora
# _Cursor es iterable, conviene que el estilo sea explicito.
fuente = (ROOT / "src/crm/db.py").read_text(encoding="utf-8")
import re
sospechosos = re.findall(r"for \w+ in conn\.execute\([^)]*\)\s*$", fuente, re.M)
check("no queda ningun `for r in conn.execute(...)` sin fetchall",
      not sospechosos, str(sospechosos))

print("\n" + "=" * 46)
print("RESULTADO:", "TODO OK" if ok else "HAY FALLOS")
print("=" * 46)
sys.exit(0 if ok else 1)
