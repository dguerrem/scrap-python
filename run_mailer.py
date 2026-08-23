"""
Entry point del mailer — Fase 6.

    python run_mailer.py --status          # Qué haría, sin enviar nada
    python run_mailer.py --tick            # Procesa como mucho 1 envío y sale
    python run_mailer.py --tick --force    # Ignora horario y ritmo (pruebas)
    python run_mailer.py --daemon          # Bucle local (equivalente al cron)
    python run_mailer.py --enqueue 20      # Encola los 20 mejores contactables
    python run_mailer.py --seed-test       # Datos de prueba con casos límite
    python run_mailer.py --reset-test      # Borra todo el rastro de la prueba
    python run_mailer.py --forget X.es     # Un dominio vuelve a ser contactable
    python run_mailer.py --autonomy        # Panel de autonomía por consola

Modos de prueba (variables de entorno):
    EMAIL_DRY_RUN=1                  no envía; escribe .eml en data/emails_out/
    EMAIL_REDIRECT_TO=tu@correo.com  envía de verdad, pero todo a tu buzón
    EMAIL_FAST_CLOCK=1               intervalos en segundos y sin horario
    EMAIL_FORCE_WINDOW=1             ignora sólo el horario L-V 8-15
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from src.crm.db import get_conn, import_leads, init_db
from src.mailer import autonomy, config, scheduler, store, templates
from src.scraper.privacy import install_log_redaction

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
install_log_redaction()  # el repo es público: nada de datos personales en CI

log = logging.getLogger("mailer")


def _avisar_modos():
    modos = config.modo_prueba_activo()
    if modos:
        log.info("MODO PRUEBA: %s", " · ".join(modos))


def cmd_status():
    st = scheduler.estado()
    aut = autonomy.resumen()
    print()
    print("=" * 52)
    print("ESTADO DEL MAILER")
    print("=" * 52)
    print(f"  Interruptor:        {'ENCENDIDO' if st['activo'] else 'apagado'}")
    dia = st["dia_warmup"]
    print(f"  Calentamiento:      {'día ' + str(dia) if dia is not None else 'sin iniciar'}")
    print(f"  Tope de hoy:        {st['enviados_hoy']}/{st['tope_diario']}")
    print(f"  Ventana horaria:    {'abierta' if st['ventana_abierta'] else 'CERRADA — ' + st['motivo_ventana']}")
    print(f"  Próximo hueco:      {st['next_send_at'] or 'ya'}"
          f"{'' if st['toca_enviar'] else '  (' + st['motivo_hueco'] + ')'}")
    print(f"  Cola:               {st['pendientes']} pendientes · "
          f"{st['enviados_total']} enviados · {st['fallidos']} fallidos")
    print(f"  Tasa de fallos:     {st['tasa_fallos'] * 100:.1f}%")
    print(f"  Último envío:       {st['ultimo_envio'] or 'nunca'}")
    if st["modos_prueba"]:
        print(f"  Modos de prueba:    {' · '.join(st['modos_prueba'])}")
    listo, motivo = config.smtp_listo()
    print(f"  SMTP:               {'configurado' if listo else 'SIN CONFIGURAR — ' + motivo}")
    print()
    print(f"  Contactables:       {aut['contactables']}")
    print(f"  Autonomía:          {aut['dias_autonomia']} días")
    if aut["ciudades_agotadas"]:
        print(f"  Ciudades agotadas:  {', '.join(aut['ciudades_agotadas'])}")
    print("=" * 52)


def cmd_autonomy():
    aut = autonomy.resumen()
    print()
    print(f"📬 Contactables ahora:   {aut['contactables']}")
    print(f"📤 Ritmo actual:         {aut['tope_diario']}/día")
    print(f"⏳ Autonomía:            {aut['dias_autonomia']} días")
    print()
    if aut["por_ciudad"]:
        print("Desglose por ciudad:")
        tope = max(aut["por_ciudad"].values())
        for ciudad, n in aut["por_ciudad"].items():
            barra = "▓" * int(10 * n / tope) if tope else ""
            print(f"  {ciudad:<28} {barra:<10} {n}")
    for ciudad in aut["ciudades_agotadas"]:
        print(f"  {ciudad:<28} {'':<10} 0  ← agotada")
    print()


def cmd_tick(forzar: bool):
    _avisar_modos()
    resultado = scheduler.tick(forzar=forzar)
    accion = resultado.get("accion")
    if accion == "sent":
        log.info("✓ %s", resultado["detalle"])
    elif accion == "failed":
        log.error("✗ %s", resultado["error"])
    elif accion == "skipped":
        log.info("○ saltado (dominio ya contactado o suprimido)")
    else:
        log.info("· sin acción: %s", resultado.get("motivo", ""))

    for aviso in autonomy.revisar_avisos():
        log.info("📨 aviso enviado: %s", aviso)
    return resultado


def cmd_daemon(intervalo: int):
    _avisar_modos()
    log.info("Daemon en marcha. Ctrl+C para parar.")
    try:
        while True:
            cmd_tick(forzar=False)
            time.sleep(intervalo)
    except KeyboardInterrupt:
        log.info("Parado.")


SEED_PERFIL = "Seed de prueba"


def cmd_enqueue(cantidad: int, perfil: str = ""):
    disponibles = autonomy.contactables()
    if perfil:
        disponibles = [l for l in disponibles
                       if (l.get("perfil_origen") or "") == perfil]
        if not disponibles:
            log.info("No hay contactables del perfil '%s'.", perfil)
            return
    elif any((l.get("perfil_origen") or "") != SEED_PERFIL for l in disponibles):
        # Encolar quema el dominio en el ledger aunque sea dry-run: es la
        # única forma de garantizar que no se llama dos veces a la misma
        # puerta. Conviene saberlo antes de gastar leads reales en una prueba.
        log.warning("Vas a encolar leads REALES. Sus dominios quedarán "
                    "gastados aunque no se envíe nada.")
        log.warning("Para probar sin gastar: --enqueue %s --perfil \"%s\"",
                    cantidad, SEED_PERFIL)
    if not disponibles:
        log.info("No hay contactables. Lanza un scrap primero.")
        return
    # Los de email directo primero: llegan a alguien con capacidad de decidir.
    disponibles.sort(key=lambda l: (not l.get("email_directo"), l["nombre"]))
    seleccion = disponibles[:cantidad]
    try:
        res = autonomy.encolar_leads(seleccion)
    except ValueError as e:
        log.error("%s Crea una plantilla o ejecuta --seed-test.", e)
        return
    log.info("Encolados %s · saltados %s", res["encolados"], res["saltados"])


def cmd_seed_test():
    """Crea leads de prueba con los casos límite del checklist del README."""
    init_db()
    leads = [
        # Directo y genérico a la vez: debe elegir el directo
        {"nombre": "Clinica Prueba Uno", "ciudad": "Pruebas",
         "direccion": "Calle Falsa 1", "email_directo": "uno@ejemplo-test.es",
         "email_generico": "info@ejemplo-test.es", "perfil_origen": "Seed de prueba"},
        # Mismo dominio que la anterior: no debe salir un segundo correo
        {"nombre": "Clinica Prueba Uno Bis", "ciudad": "Pruebas",
         "direccion": "Calle Falsa 2", "email_generico": "info@ejemplo-test.es",
         "perfil_origen": "Seed de prueba"},
        # Sólo genérico, dominio distinto
        {"nombre": "Clinica Prueba Dos", "ciudad": "Pruebas",
         "direccion": "Calle Falsa 3", "email_generico": "info@otro-test.es",
         "perfil_origen": "Seed de prueba"},
        # Dominio que va a estar en supresión
        {"nombre": "Clinica Prueba Vetada", "ciudad": "Pruebas",
         "direccion": "Calle Falsa 4", "email_directo": "hola@vetado-test.es",
         "perfil_origen": "Seed de prueba"},
        # Sin email: no debe entrar nunca en la cola
        {"nombre": "Clinica Prueba Sin Email", "ciudad": "Pruebas",
         "direccion": "Calle Falsa 5", "perfil_origen": "Seed de prueba"},
    ]
    n = import_leads(leads)
    store.suprimir("vetado-test.es", "hola@vetado-test.es", "prueba de supresión")

    if not store.plantilla_activa():
        store.guardar_plantilla(
            templates.PLANTILLA_PRUEBA["nombre"],
            templates.PLANTILLA_PRUEBA["asunto"],
            templates.PLANTILLA_PRUEBA["cuerpo"],
        )
        creada = [p for p in store.plantillas()
                  if p["nombre"] == templates.PLANTILLA_PRUEBA["nombre"]]
        if creada:
            store.activar_plantilla(creada[0]["id"])

    log.info("Sembrados %s leads de prueba + 1 dominio suprimido.", n)
    log.info("Plantilla activa: %s", (store.plantilla_activa() or {}).get("nombre"))
    log.info("Ahora: python run_mailer.py --enqueue 10 --perfil \"%s\"", SEED_PERFIL)


def cmd_reset_test():
    """Deshace --seed-test: borra los leads sembrados y todo su rastro.

    Deja la base de datos como si la prueba no hubiera existido, para poder
    repetirla las veces que haga falta.
    """
    init_db()
    conn = get_conn()
    filas = conn.execute(
        "SELECT id FROM leads WHERE perfil_origen = ?", (SEED_PERFIL,)
    ).fetchall()
    ids = [f["id"] for f in filas]

    dominios = ["ejemplo-test.es", "otro-test.es", "vetado-test.es"]
    for d in dominios:
        conn.execute("DELETE FROM email_ledger WHERE dominio = ?", (d,))
        conn.execute("DELETE FROM email_suppression WHERE dominio = ?", (d,))
        conn.execute("DELETE FROM email_queue WHERE dominio = ?", (d,))
    conn.execute("DELETE FROM leads WHERE perfil_origen = ?", (SEED_PERFIL,))
    conn.commit()
    conn.close()

    salida = Path("data/emails_out")
    borrados = 0
    if salida.exists():
        for f in salida.glob("*.eml"):
            f.unlink()
            borrados += 1

    log.info("Borrados %s leads de prueba, %s dominios y %s ficheros .eml",
             len(ids), len(dominios), borrados)


def cmd_forget(dominio: str):
    """Libera un dominio del ledger para que vuelva a ser contactable."""
    init_db()
    dominio = store.dominio_de(dominio) or dominio.strip().lower()
    if store.olvidar_ledger(dominio):
        store.log("ledger_olvidado", dominio)
        log.info("'%s' vuelve a ser contactable.", dominio)
    else:
        log.info("'%s' no estaba en el ledger.", dominio)


def main():
    parser = argparse.ArgumentParser(description="Mailer de PsycoLead")
    parser.add_argument("--tick", action="store_true", help="Procesa 1 envío y sale")
    parser.add_argument("--force", action="store_true",
                        help="Con --tick: ignora horario, ritmo y tope")
    parser.add_argument("--status", action="store_true", help="Muestra el estado")
    parser.add_argument("--autonomy", action="store_true", help="Panel de autonomía")
    parser.add_argument("--daemon", action="store_true", help="Bucle continuo")
    parser.add_argument("--interval", type=int, default=30,
                        help="Segundos entre ticks del daemon (por defecto 30)")
    parser.add_argument("--enqueue", type=int, metavar="N",
                        help="Encola los N mejores contactables")
    parser.add_argument("--perfil", default="", metavar="NOMBRE",
                        help="Con --enqueue: sólo leads de ese perfil de origen")
    parser.add_argument("--seed-test", action="store_true", dest="seed_test",
                        help="Crea datos de prueba")
    parser.add_argument("--reset-test", action="store_true", dest="reset_test",
                        help="Borra los datos de prueba y su rastro")
    parser.add_argument("--forget", metavar="DOMINIO",
                        help="Saca un dominio del ledger (vuelve a ser contactable)")
    args = parser.parse_args()

    store.asegurar_esquema()

    if args.seed_test:
        cmd_seed_test()
    elif args.reset_test:
        cmd_reset_test()
    elif args.forget:
        cmd_forget(args.forget)
    elif args.enqueue is not None:
        cmd_enqueue(args.enqueue, args.perfil)
    elif args.tick:
        cmd_tick(forzar=args.force)
    elif args.daemon:
        cmd_daemon(args.interval)
    elif args.autonomy:
        cmd_autonomy()
    else:
        cmd_status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
