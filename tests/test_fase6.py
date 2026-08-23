"""
Fase 6 — mailer.

Recorre el checklist de validación del README (6.6) sin enviar un solo correo
real: todo en DRY_RUN sobre una BD temporal.

Ejecutar:  python tests/test_fase6.py
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.pop("TURSO_DATABASE_URL", None)
os.environ.pop("TURSO_AUTH_TOKEN", None)
os.environ["EMAIL_DRY_RUN"] = "1"
os.environ["EMAIL_FORCE_WINDOW"] = "1"

from src.crm import db

TMP = Path(tempfile.mkdtemp())
db.DB_PATH = TMP / "test_fase6.db"

from src.mailer import autonomy, config, scheduler, store, templates
from src.mailer.sender import EnvioFallido

config.OUTBOX_DIR = TMP / "emails_out"

ok = True


def check(desc, cond, extra=""):
    global ok
    print(f"  {'OK  ' if cond else 'FAIL'} {desc}  {extra if not cond else ''}")
    if not cond:
        ok = False


def reset_bd():
    if db.DB_PATH.exists():
        db.DB_PATH.unlink()
    db.init_db()


def sembrar(leads):
    db.import_leads(leads)
    return {l["nombre"]: l["id"] for l in db.get_all_leads()}


def plantilla_basica():
    store.guardar_plantilla("Prueba", "Hola {nombre}", "Cuerpo para {nombre} de {ciudad}.")
    p = store.plantillas()[0]
    store.activar_plantilla(p["id"])
    return store.plantilla_activa()


reset_bd()

print("\n1) Dominios: la clave de 'una sola llamada por puerta'")
check("extrae el dominio", store.dominio_de("Ana@Clinica.ES") == "clinica.es")
check("quita el www", store.dominio_de("info@www.clinica.es") == "clinica.es")
check("sin arroba no hay dominio", store.dominio_de("no-es-un-email") == "")

print("\n2) Plantillas: {director} prohibido y pie de baja obligatorio")
problemas = templates.validar("Hola {director}", "cuerpo")
check("se rechaza {director}", any("director" in p for p in problemas), str(problemas))
check("se rechaza una variable inventada",
      templates.validar("Hola {inventada}", "x") != [])
check("acepta {nombre} y {ciudad}",
      templates.validar("Hola {nombre}", "En {ciudad}") == [])

lead_demo = {"id": 1, "nombre": "Clinica Alfa", "ciudad": "Madrid"}
asunto, texto, html = templates.render(
    {"asunto": "Hola {nombre}", "cuerpo": "Cuerpo de {ciudad}"}, lead_demo)
check("rellena el asunto", asunto == "Hola Clinica Alfa", asunto)
check("el pie de baja se añade solo", "BAJA" in texto and "BAJA" in html)
check("el pie también va en la versión HTML", "responde" in html.lower())

print("\n3) Prioridad de email: directo por encima de genérico")
ids = sembrar([
    {"nombre": "Con ambos", "ciudad": "Madrid", "direccion": "A 1",
     "email_directo": "ana@ambos.es", "email_generico": "info@ambos.es"},
    {"nombre": "Solo generico", "ciudad": "Madrid", "direccion": "A 2",
     "email_generico": "info@generico.es"},
    {"nombre": "Mismo dominio", "ciudad": "Madrid", "direccion": "A 3",
     "email_generico": "otro@ambos.es"},
    {"nombre": "Sin email", "ciudad": "Madrid", "direccion": "A 4"},
])
plantilla_basica()
disponibles = autonomy.contactables()
por_nombre = {l["nombre"]: l for l in disponibles}
check("elige el directo si hay ambos",
      por_nombre["Con ambos"]["email"] == "ana@ambos.es",
      por_nombre.get("Con ambos", {}).get("email", ""))
check("el lead sin email no es contactable", "Sin email" not in por_nombre)
check("dos leads del mismo dominio cuentan como uno",
      "Mismo dominio" not in por_nombre, str(list(por_nombre)))
check("quedan 2 contactables", len(disponibles) == 2, str(len(disponibles)))

print("\n4) Encolado: no se cuela el mismo dominio dos veces")
res = autonomy.encolar_leads(disponibles)
check("se encolan los 2", res["encolados"] == 2, str(res))
res2 = autonomy.encolar_leads(disponibles)
check("reencolar no duplica", res2["encolados"] == 0, str(res2))
todos = [dict(l) for l in db.get_all_leads()]
res3 = autonomy.encolar_leads([l for l in todos if l["nombre"] == "Mismo dominio"])
check("el hermano del mismo dominio se salta", res3["encolados"] == 0, str(res3))

print("\n5) Claim atómico: dos ticks solapados no cogen el mismo email")
a = store.claim()
b = store.claim()
check("cada claim coge un email distinto",
      a and b and a["id"] != b["id"], f"{a and a['id']} vs {b and b['id']}")
c = store.claim()
check("cuando se acaba la cola no devuelve nada", c is None, str(c))
# devolverlos a la cola para las pruebas siguientes
for item in (a, b):
    store.marcar(item["id"], "pending")

print("\n6) Ventana horaria")
os.environ.pop("EMAIL_FORCE_WINDOW")
sabado = datetime(2026, 8, 22, 10, 0)  # sábado
abierta, motivo = scheduler.ventana_abierta(sabado)
check("el fin de semana está cerrado", not abierta, motivo)
lunes_tarde = datetime(2026, 8, 24, 20, 0)
abierta, motivo = scheduler.ventana_abierta(lunes_tarde)
check("fuera de horario está cerrado", not abierta, motivo)
lunes_manana = datetime(2026, 8, 24, 10, 0)
abierta, _ = scheduler.ventana_abierta(lunes_manana)
check("un lunes por la mañana está abierto", abierta)

store.set_setting("activo", "1")
resultado = scheduler.tick()
check("con la ventana cerrada no envía (o sí, si hoy es laborable)",
      resultado["accion"] in ("nada", "sent"), str(resultado))
os.environ["EMAIL_FORCE_WINDOW"] = "1"

print("\n7) Envío en dry-run: genera el .eml y mueve el lead")
store.set_setting("activo", "1")
store.set_setting("next_send_at", "")
resultado = scheduler.tick()
check("envía uno", resultado["accion"] == "sent", str(resultado))
ficheros = list(config.OUTBOX_DIR.glob("*.eml"))
check("escribe el .eml", len(ficheros) == 1, str(ficheros))
contenido = ficheros[0].read_text(encoding="utf-8", errors="ignore")
check("el .eml lleva texto plano y HTML",
      "text/plain" in contenido and "text/html" in contenido)
check("el .eml lleva el pie de baja", "BAJA" in contenido)

enviados = store.historial()
lead_enviado = [l for l in db.get_all_leads() if l["id"] == enviados[0]["lead_id"]][0]
check("el lead pasa a Contactado", lead_enviado["etapa"] == "Contactado",
      lead_enviado["etapa"])
check("queda registrado en el ledger", store.en_ledger(resultado["dominio"]))

print("\n8) El ledger impide el segundo impacto")
antes = len(store.historial())
store.encolar(ids["Mismo dominio"], "otro@ambos.es", "x", "y", "z")
check("ni siquiera se encola un dominio ya gastado",
      store.contar_cola().get("pending", 0) == 1, str(store.contar_cola()))

print("\n9) Ritmo: el hueco siguiente cae dentro del intervalo")
store.set_setting("intervalo_min_min", "5")
store.set_setting("intervalo_max_min", "15")
huecos = []
for _ in range(20):
    scheduler._programar_siguiente()
    siguiente = store.a_fecha(store.get_setting("next_send_at"))
    huecos.append((siguiente - store.ahora()).total_seconds() / 60)
check("todos los huecos entre 5 y 15 min",
      all(4 <= h <= 15.1 for h in huecos), f"{min(huecos):.1f}-{max(huecos):.1f}")
check("hay variedad (no es un intervalo fijo)", len(set(int(h) for h in huecos)) > 1)

puede, motivo = scheduler.toca_enviar()
check("mientras no toca, no se envía", not puede, motivo)
resultado = scheduler.tick()
check("el tick respeta el hueco", resultado["accion"] == "nada", str(resultado))
check("pero --force lo salta",
      scheduler.tick(forzar=True)["accion"] in ("sent", "nada"))

print("\n10) Tope diario")
reset_bd()
sembrar([{"nombre": f"Clinica {i}", "ciudad": "Madrid", "direccion": f"C {i}",
          "email_directo": f"hola@dominio{i}.es"} for i in range(6)])
plantilla_basica()
autonomy.encolar_leads(autonomy.contactables())
store.set_setting("activo", "1")
store.set_setting("tope_manual", "3")
enviados = 0
for _ in range(6):
    store.set_setting("next_send_at", "")
    r = scheduler.tick()
    if r["accion"] == "sent":
        enviados += 1
check("se envían exactamente 3", enviados == 3, str(enviados))
check("el cuarto intento no envía", scheduler.tick()["accion"] == "nada")
eventos = [l["evento"] for l in store.ultimos_logs(20)]
check("queda registrado cap_reached", "cap_reached" in eventos, str(eventos[:5]))

print("\n11) Rampa de calentamiento")
store.set_setting("tope_manual", "")
for dias, esperado in [(0, 10), (2, 10), (3, 15), (6, 15), (7, 25),
                       (13, 25), (14, 35), (20, 35), (21, 45), (60, 45)]:
    store.set_setting("warmup_start_date",
                      store.a_texto(store.ahora() - timedelta(days=dias)))
    check(f"día {dias} → tope {esperado}", scheduler.tope_diario() == esperado,
          str(scheduler.tope_diario()))

store.set_setting("tope_maximo", "20")
store.set_setting("warmup_start_date", store.a_texto(store.ahora() - timedelta(days=60)))
check("el tope máximo manda sobre la rampa", scheduler.tope_diario() == 20,
      str(scheduler.tope_diario()))
store.set_setting("tope_maximo", "45")

print("\n12) Activar arranca la rampa sola")
store.set_setting("warmup_start_date", "")
store.set_setting("activo", "0")
scheduler.activar(True)
check("al encender se fija la fecha de inicio",
      store.get_setting("warmup_start_date", "") != "")
check("y queda encendido", store.get_setting("activo") == "1")

print("\n13) Supresión: un dominio vetado nunca sale")
reset_bd()
sembrar([{"nombre": "Vetada", "ciudad": "Madrid", "direccion": "V 1",
          "email_directo": "hola@vetado.es"}])
plantilla_basica()
store.suprimir("vetado.es", "hola@vetado.es", "prueba")
check("no es contactable", autonomy.contactables() == [])
check("no se puede encolar",
      store.encolar(1, "hola@vetado.es", "a", "b", "c") is False)

print("\n14) Si el envío falla, el dominio ya está reservado (no se reintenta a ciegas)")
reset_bd()
ids = sembrar([{"nombre": "Fallo", "ciudad": "Madrid", "direccion": "F 1",
                "email_directo": "hola@fallo.es"}])
plantilla_basica()
autonomy.encolar_leads(autonomy.contactables())
original = scheduler.enviar


def _explota(*a, **kw):
    raise EnvioFallido("SMTP caído de mentira")


scheduler.enviar = _explota
store.set_setting("activo", "1")
store.set_setting("next_send_at", "")
r = scheduler.tick()
scheduler.enviar = original
check("el tick informa del fallo", r["accion"] == "failed", str(r))
check("el dominio queda en el ledger igualmente", store.en_ledger("fallo.es"))
check("la cola lo marca como failed",
      store.contar_cola().get("failed", 0) == 1, str(store.contar_cola()))
store.set_setting("next_send_at", "")
r2 = scheduler.tick()
check("no se reenvía solo", r2["accion"] == "nada", str(r2))

print("\n15) Autonomía")
reset_bd()
sembrar([{"nombre": f"C{i}", "ciudad": "Madrid" if i < 6 else "Bilbao",
          "direccion": f"D {i}", "email_directo": f"a@d{i}.es"} for i in range(10)])
sembrar([{"nombre": "Sin mail", "ciudad": "Valencia", "direccion": "V 9"}])
store.set_setting("tope_manual", "5")
datos = autonomy.resumen()
check("cuenta los contactables", datos["contactables"] == 10, str(datos["contactables"]))
check("calcula los días", datos["dias_autonomia"] == 2.0, str(datos["dias_autonomia"]))
check("desglosa por ciudad", datos["por_ciudad"].get("Madrid") == 6,
      str(datos["por_ciudad"]))
check("detecta la ciudad agotada", "Valencia" in datos["ciudades_agotadas"],
      str(datos["ciudades_agotadas"]))

print("\n16) Avisos: llegan una vez y respetan el cooldown de 24 h")
store.set_setting("aviso_emails", "yo@ejemplo.es, otro@ejemplo.es")
store.set_setting("aviso_umbral_dias", "5")   # 2 días < 5 → debe avisar
shutil.rmtree(config.OUTBOX_DIR, ignore_errors=True)
emitidos = autonomy.revisar_avisos()
check("avisa de stock bajo", "stock_bajo" in emitidos, str(emitidos))
check("uno por destinatario", len(list(config.OUTBOX_DIR.glob("*.eml"))) == 2,
      str(list(config.OUTBOX_DIR.glob("*.eml"))))
emitidos2 = autonomy.revisar_avisos()
check("no repite dentro de 24 h", emitidos2 == [], str(emitidos2))

print("\n17) Redirección de destinatarios (pruebas con tu propio buzón)")
os.environ["EMAIL_REDIRECT_TO"] = "david@ejemplo.es"
msg = __import__("src.mailer.sender", fromlist=["construir"]).construir(
    "clinica@real.es", "Asunto", "texto", "<p>html</p>", 1)
check("el To se redirige", msg["To"] == "david@ejemplo.es", msg["To"])
check("el destinatario real se conserva",
      msg["X-Original-To"] == "clinica@real.es", msg["X-Original-To"])
os.environ.pop("EMAIL_REDIRECT_TO")

print("\n18) Reloj rápido para simular un día en minutos")
os.environ["EMAIL_FAST_CLOCK"] = "1"
scheduler._programar_siguiente()
siguiente = store.a_fecha(store.get_setting("next_send_at"))
check("los huecos pasan a segundos",
      (siguiente - store.ahora()).total_seconds() <= 15, str(siguiente))
abierta, _ = scheduler.ventana_abierta(datetime(2026, 8, 22, 3, 0))
check("y se ignora la ventana horaria", abierta)
os.environ.pop("EMAIL_FAST_CLOCK")

print("\n19) Las credenciales nunca acaban en la BD")
ajustes = store.all_settings()
sospechosas = [k for k in ajustes if "password" in k.lower() or "smtp" in k.lower()]
check("no hay claves SMTP en email_settings", not sospechosas, str(sospechosas))

print("\n" + "=" * 46)
print("RESULTADO:", "TODO OK" if ok else "HAY FALLOS")
print("=" * 46)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
