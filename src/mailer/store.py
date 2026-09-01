"""
Acceso a datos del mailer.

Todo pasa por aquí para que el resto del módulo no escriba SQL. Dos reglas
que vienen de cómo funciona Turso y que no se pueden olvidar:

1. `commit()` es un *no-op*: **no hay transacciones**. Cualquier operación que
   deba ser atómica tiene que caber en una sola sentencia.
2. Los cursores se leen con `.fetchall()` / `.fetchone()`, nunca iterándolos
   directamente (ver BUG-5).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from src.crm.db import get_conn, init_db

FMT = "%Y-%m-%d %H:%M:%S"


# ======================================================
# TIEMPO
# ======================================================

def ahora() -> datetime:
    """Instante actual en UTC, sin microsegundos."""
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)


def a_texto(dt: datetime) -> str:
    return dt.strftime(FMT)


def a_fecha(texto: str):
    if not texto:
        return None
    for fmt in (FMT, "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(texto[:26], fmt)
        except ValueError:
            continue
    return None


# ======================================================
# DOMINIOS
# ======================================================

# Proveedores públicos: el dominio no identifica a la clínica.
DOMINIOS_GENERICOS: frozenset[str] = frozenset({
    "gmail.com", "googlemail.com",
    "hotmail.com", "hotmail.es",
    "outlook.com", "outlook.es",
    "yahoo.com", "yahoo.es",
    "live.com", "live.es",
    "icloud.com", "me.com", "msn.com",
})


def clave_unica(email: str) -> str:
    """Email completo para proveedores genéricos; dominio para el resto."""
    d = dominio_de(email)
    return (email or "").strip().lower() if d in DOMINIOS_GENERICOS else d


def dominio_de(email: str) -> str:
    """Dominio normalizado de un email: minúsculas y sin `www.`.

    Es la clave de "un solo impacto por clínica": dos consultas del mismo
    grupo comparten dominio aunque tengan buzones distintos.
    """
    email = (email or "").strip().lower()
    if "@" not in email:
        return ""
    dominio = email.rsplit("@", 1)[1].strip().strip(".")
    if dominio.startswith("www."):
        dominio = dominio[4:]
    return dominio


# ======================================================
# AJUSTES
# ======================================================

def get_setting(clave: str, default: str = "") -> str:
    conn = get_conn()
    row = conn.execute(
        "SELECT valor FROM email_settings WHERE clave = ?", (clave,)
    ).fetchone()
    conn.close()
    if row is None or row["valor"] is None:
        return default
    return row["valor"]


def set_setting(clave: str, valor):
    conn = get_conn()
    # Sin transacciones: dos sentencias idempotentes en lugar de un upsert.
    conn.execute(
        "INSERT OR IGNORE INTO email_settings (clave, valor) VALUES (?, ?)",
        (clave, str(valor)),
    )
    conn.execute(
        "UPDATE email_settings SET valor = ? WHERE clave = ?",
        (str(valor), clave),
    )
    conn.commit()
    conn.close()


def all_settings() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT clave, valor FROM email_settings").fetchall()
    conn.close()
    return {r["clave"]: (r["valor"] or "") for r in rows}


def get_int(clave: str, default: int) -> int:
    try:
        return int(str(get_setting(clave, "")).strip())
    except (ValueError, TypeError):
        return default


# ======================================================
# LEDGER Y SUPRESIÓN
# ======================================================

def en_ledger(dominio: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM email_ledger WHERE dominio = ?", (dominio,)
    ).fetchone()
    conn.close()
    return row is not None


def registrar_ledger(dominio: str, email: str, lead_id=None) -> bool:
    """Reserva el dominio. Devuelve False si ya estaba reservado.

    Se llama **antes** de enviar: si el envío falla se pierde un correo, pero
    nunca se manda dos veces al mismo sitio.
    """
    conn = get_conn()
    antes = conn.execute("SELECT COUNT(*) FROM email_ledger").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO email_ledger (dominio, email, lead_id, enviado_at) "
        "VALUES (?, ?, ?, ?)",
        (dominio, email, lead_id, a_texto(ahora())),
    )
    despues = conn.execute("SELECT COUNT(*) FROM email_ledger").fetchone()[0]
    conn.commit()
    conn.close()
    return despues > antes


def olvidar_ledger(dominio: str) -> bool:
    """Libera un dominio para que vuelva a ser contactable.

    Es la marcha atrás de `registrar_ledger`. Sólo tiene sentido para deshacer
    una prueba: en producción borrar aquí significa arriesgarse a llamar dos
    veces a la misma puerta.
    """
    conn = get_conn()
    antes = conn.execute("SELECT COUNT(*) FROM email_ledger").fetchone()[0]
    conn.execute("DELETE FROM email_ledger WHERE dominio = ?", (dominio,))
    despues = conn.execute("SELECT COUNT(*) FROM email_ledger").fetchone()[0]
    conn.commit()
    conn.close()
    return despues < antes


def en_supresion(dominio: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM email_suppression WHERE dominio = ?", (dominio,)
    ).fetchone()
    conn.close()
    return row is not None


def suprimir(dominio: str, email: str = "", motivo: str = "") -> None:
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO email_suppression (dominio, email, motivo, created_at) "
        "VALUES (?, ?, ?, ?)",
        (dominio, email, motivo, a_texto(ahora())),
    )
    conn.commit()
    conn.close()


def listar_supresion() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM email_suppression ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def quitar_supresion(dominio: str):
    conn = get_conn()
    conn.execute("DELETE FROM email_suppression WHERE dominio = ?", (dominio,))
    conn.commit()
    conn.close()


# ======================================================
# COLA
# ======================================================

def encolar(lead_id: int, destinatario: str, asunto: str,
            cuerpo_texto: str, cuerpo_html: str) -> bool:
    """Mete un lead en la cola. False si ya estaba o si el dominio está vetado."""
    dominio = dominio_de(destinatario)
    if not dominio:
        return False
    # Para dominios genéricos la clave es el email; para corporativos, el dominio.
    clave = clave_unica(destinatario)
    if en_ledger(clave) or en_supresion(dominio):
        return False

    conn = get_conn()
    antes = conn.execute("SELECT COUNT(*) FROM email_queue").fetchone()[0]
    # El índice único parcial sobre (dominio) para estados pending/sending
    # impide encolar dos veces la misma clínica aunque llamemos dos veces.
    conn.execute(
        "INSERT OR IGNORE INTO email_queue "
        "(lead_id, destinatario, dominio, asunto, cuerpo_texto, cuerpo_html, "
        " estado, created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
        (lead_id, destinatario, clave, asunto, cuerpo_texto, cuerpo_html,
         a_texto(ahora())),
    )
    despues = conn.execute("SELECT COUNT(*) FROM email_queue").fetchone()[0]
    conn.commit()
    conn.close()
    return despues > antes


def claim() -> dict | None:
    """Reserva un email de la cola de forma atómica.

    `TursoConnection.commit()` no hace nada, así que un SELECT seguido de
    UPDATE permitiría que dos ticks solapados enviaran el mismo correo. Se
    hace todo en una sentencia y luego se lee por el token, que es único de
    esta llamada: si otro proceso ganó la carrera, aquí no aparece nada.
    """
    token = uuid.uuid4().hex
    conn = get_conn()
    conn.execute(
        """
        UPDATE email_queue
           SET estado = 'sending',
               intentos = intentos + 1,
               claim_token = ?,
               claimed_at = ?
         WHERE id = (SELECT id FROM email_queue
                      WHERE estado = 'pending'
                      ORDER BY id LIMIT 1)
           AND estado = 'pending'
        """,
        (token, a_texto(ahora())),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM email_queue WHERE claim_token = ?", (token,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def liberar_atascados(minutos: int = 15) -> int:
    """Devuelve a 'pending' lo que se quedó en 'sending' (proceso muerto)."""
    limite = a_texto(ahora() - timedelta(minutes=minutos))
    conn = get_conn()
    afectados = conn.execute(
        "SELECT COUNT(*) FROM email_queue "
        "WHERE estado = 'sending' AND (claimed_at IS NULL OR claimed_at < ?) "
        "AND intentos < 3",
        (limite,),
    ).fetchone()[0]
    if afectados:
        conn.execute(
            "UPDATE email_queue SET estado = 'pending', claim_token = '' "
            "WHERE estado = 'sending' AND (claimed_at IS NULL OR claimed_at < ?) "
            "AND intentos < 3",
            (limite,),
        )
        conn.commit()
    conn.close()
    return afectados


def marcar(queue_id: int, estado: str, error: str = ""):
    conn = get_conn()
    conn.execute(
        "UPDATE email_queue SET estado = ?, error = ?, sent_at = ? WHERE id = ?",
        (estado, error, a_texto(ahora()) if estado == "sent" else None, queue_id),
    )
    conn.commit()
    conn.close()


def cola(estado: str = "", limite: int = 200) -> list:
    conn = get_conn()
    if estado:
        rows = conn.execute(
            "SELECT * FROM email_queue WHERE estado = ? ORDER BY id LIMIT ?",
            (estado, limite),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM email_queue ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def contar_cola() -> dict:
    conn = get_conn()
    rows = conn.execute(
        "SELECT estado, COUNT(*) FROM email_queue GROUP BY estado"
    ).fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def borrar_de_cola(queue_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM email_queue WHERE id = ?", (queue_id,))
    conn.commit()
    conn.close()


def reintentar_fallidos() -> int:
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM email_queue WHERE estado = 'failed'"
    ).fetchone()[0]
    if n:
        conn.execute(
            "UPDATE email_queue SET estado = 'pending', error = '', "
            "intentos = 0, claim_token = '' WHERE estado = 'failed'"
        )
        conn.commit()
    conn.close()
    return n


# ======================================================
# LOG Y CONTADORES
# ======================================================

def log(evento: str, detalle: str = "", queue_id=None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO email_log (queue_id, evento, detalle, created_at) "
        "VALUES (?, ?, ?, ?)",
        (queue_id, evento, detalle, a_texto(ahora())),
    )
    conn.commit()
    conn.close()


def ultimos_logs(limite: int = 50) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM email_log ORDER BY id DESC LIMIT ?", (limite,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def enviados_entre(desde: datetime, hasta: datetime) -> int:
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM email_ledger WHERE enviado_at >= ? AND enviado_at < ?",
        (a_texto(desde), a_texto(hasta)),
    ).fetchone()[0]
    conn.close()
    return n


def ultimo_envio() -> datetime | None:
    conn = get_conn()
    row = conn.execute("SELECT MAX(enviado_at) FROM email_ledger").fetchone()
    conn.close()
    return a_fecha(row[0]) if row and row[0] else None


def historial(limite: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT l.*, le.nombre, le.ciudad FROM email_ledger l "
        "LEFT JOIN leads le ON le.id = l.lead_id "
        "ORDER BY l.id DESC LIMIT ?",
        (limite,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ======================================================
# PLANTILLAS
# ======================================================

def plantillas() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM email_templates ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def plantilla_activa() -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM email_templates WHERE activa = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def guardar_plantilla(nombre: str, asunto: str, cuerpo: str,
                      plantilla_id=None) -> int:
    conn = get_conn()
    if plantilla_id:
        conn.execute(
            "UPDATE email_templates SET nombre = ?, asunto = ?, cuerpo = ? WHERE id = ?",
            (nombre, asunto, cuerpo, plantilla_id),
        )
    else:
        conn.execute(
            "INSERT INTO email_templates (nombre, asunto, cuerpo, activa) "
            "VALUES (?, ?, ?, 0)",
            (nombre, asunto, cuerpo),
        )
    conn.commit()
    conn.close()
    return plantilla_id or 0


def activar_plantilla(plantilla_id: int):
    conn = get_conn()
    conn.execute("UPDATE email_templates SET activa = 0")
    conn.execute("UPDATE email_templates SET activa = 1 WHERE id = ?", (plantilla_id,))
    conn.commit()
    conn.close()


def borrar_plantilla(plantilla_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM email_templates WHERE id = ?", (plantilla_id,))
    conn.commit()
    conn.close()


def asegurar_esquema():
    """Atajo para los entry points: crea tablas si aún no existen."""
    init_db()
