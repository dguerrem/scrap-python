# Mailer en el VPS

Guía operativa del scheduler de correo de PsycoLead desplegado en el VPS.

## Estado actual

El mailer está instalado de forma aislada y no modifica Nginx, PM2, MariaDB, el ERP, la red ni la zona horaria del servidor.

| Elemento | Configuración |
| --- | --- |
| Usuario del sistema | `psycolead` (sin privilegios) |
| Aplicación | `/opt/psycolead/app` |
| Python | `/opt/psycolead/venv/bin/python` (Python 3.12) |
| Credenciales | `/etc/psycolead-mailer.env` (`root:root`, permisos `600`) |
| Base de datos | Turso; no se usa el SQLite local |
| Servicio | `psycolead-mailer.service` (`oneshot`) |
| Timer | `psycolead-mailer.timer` |
| Scheduler anterior | Workflow `Mailer` de GitHub Actions deshabilitado |

El timer se conserva tras reiniciar el VPS.

## Funcionamiento

Systemd inicia un tick cada minuto, de lunes a viernes entre las 08:00 y las 18:59, usando explícitamente `Europe/Madrid`. Cada tick termina después de comprobar el estado.

El scheduler de Python decide si corresponde enviar:

- Como máximo un correo por tick.
- Separación aleatoria persistida de 5 a 15 minutos.
- Ventana real de 08:00 a 19:00, hora de Madrid.
- Tope diario según la rampa de calentamiento.
- Tope máximo configurado de 45 correos diarios.
- Un único contacto por dominio mediante el ledger.
- Si la cola está vacía o todavía no toca, no envía nada.

El tick no ejecuta el scraper, Playwright, Streamlit ni procesos del ERP. Funciona con prioridad reducida (`Nice=10`) y systemd no solapa dos ejecuciones de la misma unidad.

## Comprobar que funciona

Estado del timer:

```bash
systemctl is-enabled psycolead-mailer.timer
systemctl is-active psycolead-mailer.timer
systemctl list-timers --all psycolead-mailer.timer --no-pager
```

El resultado normal es `enabled`, `active` y una fecha en `NEXT` durante la ventana de ejecución.

Resultado del último tick:

```bash
systemctl show psycolead-mailer.service \
  -p Result -p ExecMainStatus -p ActiveState -p SubState \
  -p ExecMainStartTimestamp -p ExecMainExitTimestamp
```

Después de terminar, el estado normal del servicio es:

```text
Result=success
ExecMainStatus=0
ActiveState=inactive
SubState=dead
```

`inactive/dead` es correcto: el servicio es `oneshot`, no un proceso permanente. El timer es quien debe permanecer `active`.

Estado funcional del mailer, la cola y el siguiente hueco:

```bash
(
  set -a
  . /etc/psycolead-mailer.env
  set +a

  runuser -u psycolead --preserve-environment -- \
    /opt/psycolead/venv/bin/python \
    /opt/psycolead/app/run_mailer.py --status
)
```

Este comando solo consulta el estado; no procesa la cola.

Logs recientes:

```bash
journalctl -u psycolead-mailer.service --since today --no-pager
```

## Pararlo

Parada permanente, incluida después de reiniciar el VPS:

```bash
systemctl disable --now psycolead-mailer.timer
```

Comprobar la parada:

```bash
systemctl is-enabled psycolead-mailer.timer || true
systemctl is-active psycolead-mailer.timer || true
```

Debe mostrar `disabled` e `inactive`.

También se puede apagar el interruptor maestro desde el tab `Emails` del CRM. En ese caso el timer continúa haciendo comprobaciones, pero no envía. Para una parada de infraestructura completa, usar `disable --now`.

## Volver a arrancarlo

Antes de arrancar, confirmar que el workflow `Mailer` de GitHub Actions continúa deshabilitado. Después:

```bash
systemctl enable --now psycolead-mailer.timer
systemctl is-enabled psycolead-mailer.timer
systemctl is-active psycolead-mailer.timer
```

Debe mostrar `enabled` y `active`.

## Operación habitual

La tarea manual es mantener contactos en la cola:

1. Enriquecer e importar nuevos leads cuando se agoten los disponibles.
2. Encolar desde el tab `Emails` únicamente los leads que se quieran contactar.
3. Revisar respuestas, bajas y rebotes.
4. Vigilar periódicamente el historial y los fallos del mailer.

Encolar reserva el dominio para proteger la regla de un único impacto por clínica, incluso en pruebas. No usar el encolado como previsualización.

## Precauciones imprescindibles

- No habilitar a la vez el workflow `Mailer` de GitHub Actions y el timer del VPS. Ambos usan Turso y competirían por la misma cola.
- No ejecutar `systemctl start psycolead-mailer.service` como prueba: inicia un tick real y puede enviar un correo.
- No usar `run_mailer.py --tick`, `--force` o `--enqueue` para comprobar el estado.
- No imprimir, copiar ni versionar `/etc/psycolead-mailer.env`. Contiene los secretos de Turso y SMTP.
- Mantener `/etc/psycolead-mailer.env` como `root:root` con permisos `600`.
- Si cambia una credencial, editar el archivo y validar con `--status`; no es necesario reiniciar el timer porque cada tick carga de nuevo el entorno.
- La contraseña de aplicación SMTP que apareció en una conversación debe considerarse expuesta. Rotarla sigue siendo la recomendación de seguridad.
- La cola, los límites, el horario, `next_send_at` y el ledger viven en Turso. No borrar ni reemplazar esa base de datos sin restaurar primero el ledger y las supresiones.

## Archivos de systemd

```text
/etc/systemd/system/psycolead-mailer.service
/etc/systemd/system/psycolead-mailer.timer
```

Después de modificar cualquiera de ellos:

```bash
systemd-analyze verify \
  /etc/systemd/system/psycolead-mailer.service \
  /etc/systemd/system/psycolead-mailer.timer
systemctl daemon-reload
systemctl restart psycolead-mailer.timer
```

Reiniciar el timer no procesa la cola inmediatamente; solo vuelve a programar la próxima ejecución.
