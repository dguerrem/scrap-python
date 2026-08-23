#!/usr/bin/env python3
"""Backup de la base de datos.

Exporta todas las tablas a un único JSON. No cifra ni sube nada: de eso se
encarga el workflow, porque el fichero lleva emails y notas comerciales y este
repositorio es público.

    python run_backup.py                 # -> data/backup/backup-AAAA-MM-DD.json
    python run_backup.py --salida x.json
    python run_backup.py --restaurar x.json --tabla email_ledger

La prioridad al restaurar es siempre la misma: primero `email_ledger` y
`email_suppression`. Sin esas dos se le escribiría dos veces a la misma
clínica, que es lo único que este sistema no puede permitirse.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.crm import db  # noqa: E402

# En orden de criticidad: si una restauración se corta a medias, lo que ya
# se haya escrito es lo que más falta hacía.
TABLAS = [
    "email_ledger",
    "email_suppression",
    "leads",
    "email_settings",
    "email_templates",
    "scrap_profiles",
    "app_links",
    "email_log",
]


def exportar() -> dict:
    db.init_db()
    conn = db.get_conn()
    datos = {
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": 1,
        "tablas": {},
    }
    for tabla in TABLAS:
        try:
            filas = conn.execute(f"SELECT * FROM {tabla}").fetchall()
            datos["tablas"][tabla] = [dict(f) for f in filas]
        except Exception as e:
            print(f"  aviso: no se pudo exportar {tabla}: {e}")
            datos["tablas"][tabla] = []
    conn.close()
    return datos


def restaurar(ruta: Path, solo: list) -> None:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    db.init_db()
    conn = db.get_conn()
    for tabla in TABLAS:
        if solo and tabla not in solo:
            continue
        filas = datos.get("tablas", {}).get(tabla, [])
        if not filas:
            continue
        columnas = list(filas[0].keys())
        marcas = ",".join("?" for _ in columnas)
        sql = (f"INSERT OR IGNORE INTO {tabla} ({','.join(columnas)}) "
               f"VALUES ({marcas})")
        n = 0
        for fila in filas:
            try:
                conn.execute(sql, [fila.get(c) for c in columnas])
                n += 1
            except Exception as e:
                print(f"  aviso: fila de {tabla} descartada: {e}")
        conn.commit()
        print(f"  {tabla}: {n} filas restauradas")
    conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Backup de la base de datos")
    p.add_argument("--salida", help="Fichero JSON de destino")
    p.add_argument("--restaurar", help="Fichero JSON a restaurar")
    p.add_argument("--tabla", action="append", default=[],
                   help="Restaurar sólo estas tablas (repetible)")
    args = p.parse_args()

    if args.restaurar:
        ruta = Path(args.restaurar)
        if not ruta.exists():
            print(f"No existe {ruta}")
            return 1
        print(f"Restaurando desde {ruta}")
        restaurar(ruta, args.tabla)
        return 0

    datos = exportar()
    if args.salida:
        destino = Path(args.salida)
    else:
        hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        destino = Path("data/backup") / f"backup-{hoy}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=1),
                       encoding="utf-8")

    for tabla, filas in datos["tablas"].items():
        print(f"  {tabla}: {len(filas)}")
    print(f"Backup en {destino} ({destino.stat().st_size / 1024:.0f} KB)")

    # Se guarda la fecha para poder enseñarla en la Guía sin abrir el backup.
    try:
        from src.mailer import store
        store.set_setting("ultimo_backup", datos["generado"])
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
