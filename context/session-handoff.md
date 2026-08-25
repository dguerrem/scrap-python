# Contexto de continuidad — para retomar la conversación sin fricción

> Este fichero es un "puente" entre chats. Léelo entero antes de responder nada.
> Está escrito para que la siguiente sesión pueda seguir exactamente donde se
> quedó, con el mismo tono (breve, "caveman", explicaciones sencillas) y sin
> repetir preguntas ya respondidas.

## Quién es el usuario y cómo tratarlo

David Guerrero. No es programador de formación ("caveman" con el código, sus
palabras). Pide explicaciones **breves y sencillas**, sin jerga innecesaria.
Valida los cambios probándolos él mismo (en local o en la app cloud). Prefiere
que primero se le explique qué es algo y para qué sirve, y luego el cómo.

## Qué es el proyecto

**PsycoLead-Scraper**: pipeline de scraping (Google Maps) + enriquecimiento
web + CRM en Streamlit, para prospectar clínicas de psicología en España y
vender **PsycoERP**, un ERP de gestión para clínicas (2.500 € pago único, sin
suscripción). El objetivo de negocio: 3-5 clientes/mes mediante prospección
outbound (scraping → email frío automatizado → vídeo Loom → llamada → demo →
cierre).

**El README.md del repo (~1.400 líneas) es el documento maestro.** Tiene todo
el plan de desarrollo por fases, el diseño técnico completo del mailer, las
decisiones de diseño y sus motivos, y los comandos. Ante cualquier duda sobre
"por qué se hizo así", **leer el README primero**.

## Restricciones permanentes (no negociables)

- Todo debe funcionar **igual en local (SQLite) y en cloud (Turso + GitHub
  Actions)**. Turso no tiene transacciones reales (`commit()`/`close()` son
  no-op) — todo lo atómico tiene que caber en una sola sentencia SQL.
- El proyecto debe ser **gratis y autónomo siempre** (capas gratuitas de
  Streamlit Cloud, Turso, GitHub Actions).
- El repositorio es **público**. Nunca credenciales, datos personales de
  leads, ni nada sensible en código, logs, commits o artifacts.
- **Regla de negocio inamovible del mailer:** un email por dominio, jamás
  repetido. Mejor perder un envío que duplicarlo.

## Dónde estamos: Fases 4, 5 y 6 completas, cerrando validación

| Fase | Qué es | Estado |
|---|---|---|
| 4 | Bugs + riesgos de seguridad | ✅ Cerrada, validada en producción |
| 5 | Refactor UI (`app.py` → `views/`) + tab 📖 Guía | ✅ Desplegada, aprobada |
| 6 | Motor de envío de emails | ✅ Código completo y testeado. **En proceso de validación con envíos reales antes de activar en producción** |

Todo el trabajo de Fase 6 está **commiteado y pusheado** (últimos commits:
`1ee751b feat(): Mailing System`, `489327e fix(): Switch Mailer On/Off`).
Working tree limpio.

## Fase 6 — estado exacto ahora mismo

**El mailer está en producción pero apagado y no puede enviar nada.** Cuatro
cerrojos independientes: interruptor `activo=0`, sin plantilla real activa en
Turso (solo hay plantillas de prueba en local), cola vacía en Turso, y aunque
se enciende no hay tope forzado (`tope_manual` vacío → usaría la rampa).

El cron de GitHub Actions (`mailer.yml`) corre cada 5 min de lunes a viernes,
ve el interruptor apagado vía `run_mailer.py --gate` y **sale en verde sin
hacer nada**. Esto es intencionado y está verificado, no es un bug.

### Lo que se ha validado ya en local
- Todo el motor: dedup por dominio, claim atómico, ventana horaria, rampa de
  calentamiento, tope diario, plantillas, pie de baja — 7 ficheros de test
  (`tests/*.py`), todos en verde.
- Checklist 6.0 (config externa de Google) completo por el usuario:
  2FA ✅, DKIM verificado y activo ✅, contraseña de aplicación generada ✅,
  `.streamlit/secrets.toml` local ya tiene las credenciales SMTP puestas.
- **Envío real por SMTP probado**: con `EMAIL_REDIRECT_TO`, un correo salió
  de verdad desde `info@psycoerp.es` y llegó al Gmail personal del usuario
  (cayó en Promociones la primera vez — esperable con un dominio sin
  historial; no es indicativo de un fallo real, ver sección de
  entregabilidad más abajo).

### La plantilla de email actual (ya escrita, aprobada por el usuario)

Guardada localmente como **"Correo frio v1"** y activa. Este es el texto
definitivo hasta que se decida cambiarlo:

**Asunto:** `Ideas para simplificar la gestión de {nombre}`

**Cuerpo:**
```
Hola {nombre},

Soy David Guerrero, fundador de PsycoERP. Escribo directamente a clínicas de psicología de {ciudad}, sin pasar por llamadas ni intermediarios.

Muchas clínicas de varios profesionales acaban con dos problemas: plataformas genéricas que no encajan con su forma de repartir salas y comisiones, y sus datos de pacientes guardados en servidores de terceros.

PsycoERP es un software de gestión hecho a medida de vuestro flujo real —citas, comisiones, pacientes, facturación—, de pago único (no suscripción) e instalado en un servidor a vuestro nombre. La migración de vuestros datos actuales y la formación van incluidas, sin coste.

Si os interesa, respondedme a este correo y os cuento más.

Un saludo,
David Guerrero
Fundador de PsycoERP
https://psycoerp.es
```

Decisiones tomadas sobre este texto (no volver a preguntar):
- Tuteo, no "usted".
- Saludo con el **nombre de la clínica**, no del director (el dato de
  director tiene baja fiabilidad — ver README, decisión de diseño).
- **Sin precio** en el primer correo (ni la cifra ni "pago único" con
  detalle económico más allá de mencionar que no es suscripción).
- CTA de máxima baja fricción: solo pide responder al correo, nada de
  agendar llamada ni pedir ver el vídeo Loom en este primer contacto.
- Un solo enlace (la web), sin imágenes ni logo — cualquier adorno visual
  sube el spam score en frío.
- El pie de baja **lo añade el motor automáticamente**, no está en este
  texto ni se puede quitar desde la UI.

### Siguiente paso pendiente (lo próximo a hacer)

El usuario pidió explícitamente: **antes de activar en producción, pasarle
tests de entregabilidad y formato al correo para evitar que cualquier
proveedor lo mande a Promociones/Spam.** Esto es lo primero que hay que
retomar. Ideas a explorar (sin implementar aún, pendiente de decidir con el
usuario):

- Revisar el HTML del pie de baja: el separador con `border-top` y el estilo
  gris parecen firma de newsletter aunque el contenido no lo sea — probar a
  simplificarlo para que parezca más una firma de correo normal.
- Herramientas de verificación gratuitas a considerar: `mail-tester.com`
  (da una puntuación 1-10 y explica qué falla: SPF/DKIM/DMARC, spam words,
  HTML válido, etc.) — se puede probar mandando un correo de prueba a la
  dirección que da la herramienta.
- Confirmar que **SPF y DMARC** (no solo DKIM) están bien publicados en el
  DNS de `psycoerp.es` — DKIM ya se verificó, SPF/DMARC no se ha comprobado
  explícitamente en esta sesión.
- Recordar: la pestaña Promociones es una función de Gmail **personal**
  (`@gmail.com`); las cuentas de empresa en Google Workspace normalmente no
  la tienen. Puede que en producción (contactos con dominio propio) esto ni
  se note. No sobre-optimizar para un caso que quizá no aplique al target
  real.
- Solo cuando el usuario dé el OK al formato: prueba de humo en producción
  con `tope_manual = 2` (ver checklist 6.0 punto 6 en el README).

## Comandos que se van a necesitar

Entorno: macOS, Python del proyecto en `./venv/bin/python` (NO usar el
`python` del sistema, es 2.x). `timeout` no existe en este shell; `kill`
necesita PID numérico (`lsof -ti :8501`); `pkill`/`killall` prohibidos.

```bash
cd /Users/dguerrero/Desktop/Everything/Projects/Psyco/scrap-python

# --- CRM en local (SQLite, no toca Turso) ---
./venv/bin/streamlit run src/crm/app.py        # http://localhost:8501

# --- Tests (7 ficheros, deben estar todos en verde) ---
for t in tests/*.py; do ./venv/bin/python $t; done

# --- Mailer: probar con datos falsos, sin gastar leads reales ---
./venv/bin/python run_mailer.py --reset-test      # limpia rastro de pruebas anteriores
./venv/bin/python run_mailer.py --seed-test       # 5 leads falsos con casos límite
./venv/bin/python run_mailer.py --enqueue 10 --perfil "Seed de prueba"
EMAIL_DRY_RUN=1 ./venv/bin/python run_mailer.py --tick --force   # -> data/emails_out/*.eml
open data/emails_out/                             # ver el .eml como llegaría

# --- Mailer: envío REAL de prueba, pero todo cae en tu propio buzón ---
EMAIL_REDIRECT_TO=dacormus@gmail.com ./venv/bin/python run_mailer.py --tick --force

# --- Estado y autonomía ---
./venv/bin/python run_mailer.py --status
./venv/bin/python run_mailer.py --autonomy

# --- Deshacer una reserva accidental del ledger ---
./venv/bin/python run_mailer.py --forget dominio.es

# --- Backup manual ---
./venv/bin/python run_backup.py
```

**Cuidado:** `export EMAIL_DRY_RUN=1` hecho con `export` en una terminal se
queda pegado a esa sesión de shell hasta que se hace `unset EMAIL_DRY_RUN` o
se cierra la ventana. Si un envío que debería ser real sigue escribiendo
`.eml`, es casi siempre por esto.

**Cuidado 2:** `--enqueue` **sin** `--perfil "Seed de prueba"` coge leads
reales de Turso/local y reserva su dominio en el ledger aunque sea dry-run
— es intencionado (garantiza no duplicar), pero quema un lead real por
error si no se pone el filtro de perfil en las pruebas.

## Mapa de ficheros clave de la Fase 6

```
src/mailer/
  config.py     — credenciales SMTP desde entorno/secrets.toml, modos de prueba
  store.py      — único punto de SQL del mailer (ledger, cola, supresión, ajustes)
  templates.py  — validación + render + pie de baja automático
  sender.py     — construcción MIME + envío SMTP + dry-run a .eml
  scheduler.py  — ventana horaria, rampa, tope diario, jitter, tick()
  autonomy.py   — contactables, resumen, encolado, avisos de stock bajo
run_mailer.py   — CLI (--status --tick --gate --enqueue --seed-test --reset-test --forget ...)
run_backup.py   — export/restore de toda la BD a JSON
src/crm/views/emails.py       — tab 📧 Emails de la UI
.github/workflows/mailer.yml  — cron cada 5 min L-V, con --gate como portero
.github/workflows/backup.yml  — backup cifrado semanal + keepalive
tests/test_fase6.py — 60+ comprobaciones del mailer
tests/test_bug5.py  — arnés de paridad local/cloud (bloque 8 cubre el mailer)
```

## Decisiones técnicas que no hay que volver a explicar ni cuestionar

- Ledger se escribe **antes** de enviar (mejor perder un correo que
  duplicarlo).
- Dedup por **dominio**, no por email (dos clínicas del mismo grupo = un
  solo impacto).
- Cabecera `List-Unsubscribe` añadida en `sender.py` además del pie de texto
  (Gmail/Outlook puntúan la baja en un clic).
- El `--gate` en `run_mailer.py` existe porque sin él el cron fallaba en rojo
  ~120 veces/día con el mailer apagado, y GitHub avisaba por correo cada vez.
- El backup se cifra con GPG (`BACKUP_PASSPHRASE` como secret) y sube como
  artifact, no a un repo separado — más simple de mantener.
- Ver README, sección "Decisiones de diseño tomadas", para el resto (hay
  una tabla completa con motivo de cada decisión).
