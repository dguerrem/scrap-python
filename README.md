# PsycoLead-Scraper

Pipeline de extracción, enriquecimiento y contacto de leads B2B para la prospección de clínicas de psicología en España. Motor comercial de **PsycoERP**.

---

## Índice

- [Contexto del producto](#contexto-del-producto-psycoerp)
- [Cliente ideal (ICP)](#cliente-ideal-icp)
- [Estrategia de prospección](#estrategia-de-prospección-go-to-market)
- [Stack tecnológico](#stack-tecnológico)
- [Arquitectura actual](#arquitectura-actual)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Estado actual — Fases 0-3 ✅](#estado-actual--fases-0-3-)
- [Bugs detectados](#bugs-detectados)
- [Riesgos y sostenibilidad](#riesgos-y-sostenibilidad)
- [Plan de desarrollo](#plan-de-desarrollo)
  - [Fase 4 — Corrección de bugs y exposición](#fase-4--corrección-de-bugs-y-exposición)
  - [Fase 5 — Refactor de UI + Guía rápida](#fase-5--refactor-de-ui--guía-rápida)
  - [Fase 6 — Módulo de envío de emails](#fase-6--módulo-de-envío-de-emails)
  - [Fase 7 — Backlog documentado](#fase-7--backlog-documentado-no-se-implementa)
- [Orden de trabajo](#orden-de-trabajo)
- [Decisiones de diseño tomadas](#decisiones-de-diseño-tomadas)

---

## Contexto del Producto: PsycoERP

Software de gestión (ERP) nicho diseñado exclusivamente para psicólogos y clínicas de salud mental, bajo modelo **High-Ticket de pago único** (2.500 € por licencia).

### Módulos principales

- Calendario y gestión de citas.
- Gestión de llamadas y recordatorios automáticos (API tipo Twilio / 360dialog).
- Gestión de pacientes e historial clínico (cumplimiento LOPD/RGPD).
- Gestión de sesiones.
- Dashboard analítico con métricas de negocio y comisiones de terapeutas.
- Módulo de facturación (opcional/configurable).

### Modelo de negocio

- **Precio:** 2.500 € (pago único, sin suscripción).
- **Propuesta de valor:** el software es 100 % del cliente y adaptado a sus flujos reales. Se amortiza en menos de 10 meses frente a SaaS genéricos (~3.000 € a 5 años).
- **Servicio incluido:** soporte 24/7 y mantenimiento el primer año + migración de datos históricos y formación ("Guante Blanco") a coste cero.
- **Infraestructura:** el ERP se instala en un VPS a nombre del cliente (~10 €/mes) con sus propias cuentas de API.

---

## Cliente Ideal (ICP)

- **Target:** clínicas de psicología medianas (gabinetes de 3 a 15 profesionales).
- **Motivación:** flujos complejos de reparto de salas y comisiones; hartos de suscripciones eternas a plataformas genéricas con sus datos en servidores de terceros.
- **Gatekeeper:** recepcionistas que filtran llamadas → la prospección evita el teléfono a puerta fría y la bandeja `info@`.

---

## Estrategia de Prospección (Go-To-Market)

Objetivo: **3-5 clientes mensuales** mediante prospección outbound quirúrgica.

1. **Extracción Local** — Scraping de clínicas en Google Maps.
2. **Enriquecimiento** — Nombre del Director/Propietario + email directo.
3. **Contacto Asíncrono** — Email frío automatizado (1 único impacto por clínica) → Video-Pitch de 2 min (Loom).
4. **Cierre** — Llamada de descubrimiento (15 min) → Demo → Cierre a 2.500 €.

---

## Stack Tecnológico

| Componente        | Tecnología                          |
| ----------------- | ----------------------------------- |
| Lenguaje          | Python 3.9+ (3.11 en CI)            |
| Scraping core     | Playwright (headless)               |
| CRM               | Streamlit                           |
| BD local          | SQLite (`data/crm.db`)              |
| BD cloud          | Turso / libSQL (cliente HTTP propio)|
| Orquestación      | GitHub Actions (`workflow_dispatch` + `schedule`) |
| Envío de email    | `smtplib` + SMTP de Google Workspace |
| Salida de datos   | JSON / CSV                          |

> **Principio:** todo debe funcionar **igual en local (SQLite) y en cloud (Turso + Actions)**. Un solo camino de código.

---

## Arquitectura actual

```
┌─────────────────────────┐         ┌──────────────────┐
│  CRM Streamlit          │────────▶│  SQLite  (local) │
│  src/crm/app.py         │         │  Turso   (cloud) │
└───────────┬─────────────┘         └──────────────────┘
            │                                 ▲
            │ launch() / launch_cloud()       │
            ▼                                 │
┌─────────────────────────┐                   │
│  pipeline_runner.py     │                   │
│  · local → subprocess   │                   │
│  · cloud → GH API       │                   │
└───────────┬─────────────┘                   │
            ▼                                 │
┌─────────────────────────┐                   │
│  GitHub Actions         │                   │
│  .github/workflows/     │───────────────────┘
│    pipeline.yml         │   auto-import a Turso
└───────────┬─────────────┘
            ▼
   run_scraper.py → maps_scraper.py  → data/leads_raw.json
   run_enricher.py → enricher.py     → data/leads_enriched.json
```

### Flujo perfil → ejecución

1. Se define un **perfil de scrap** en el CRM (tabla `scrap_profiles`).
2. `pipeline_runner.launch()` genera un `run_id` (`YYYYMMDD-HHMM-slug`) y escribe `data/active_profile.json`.
3. El script lee el perfil y **sobreescribe los defaults** de `config.py`.
4. Los outputs se versionan en `data/runs/{run_id}-{raw|enriched}.{json|csv}`.
5. La importación al CRM etiqueta cada lead con `perfil_origen` para trazabilidad.

---

## Estructura del Proyecto

```
scrap-python/
├── context/                      # Briefing y notas de producto
│   ├── briefing.txt
│   ├── How_To.md                 # Comandos locales
│   ├── next-steps.md             # Backlog de features del CRM
│   └── github-actions-plan.md    # Diseño de la automatización
├── src/
│   ├── scraper/
│   │   ├── maps_scraper.py       # Fase 1: Scraping Google Maps
│   │   ├── enricher.py           # Fase 2: Enriquecimiento webs
│   │   └── config.py             # Ciudades, filtros, delays, user-agents
│   ├── crm/
│   │   ├── app.py                # Fase 3: CRM Streamlit
│   │   ├── db.py                 # Capa de datos (SQLite / Turso)
│   │   ├── turso_http.py         # Cliente HTTP libSQL sin deps nativas
│   │   └── pipeline_runner.py    # Lanzador local (subprocess) y cloud (GH API)
│   └── models/
│       └── lead.py               # Dataclass Lead
├── .github/workflows/pipeline.yml
├── .streamlit/                   # config.toml + secrets.toml.example
├── data/                         # Output (gitignored)
├── run_scraper.py
├── run_enricher.py
├── run_pipeline.py
└── requirements.txt
```

---

## Estado actual — Fases 0-3 ✅

| Fase | Descripción | Estado |
| ---- | ----------- | ------ |
| **0** | Setup del entorno, venv, Playwright | ✅ |
| **1** | Minería en Google Maps (filtros, scroll, dedup) | ✅ |
| **2** | Enriquecimiento (director vía Aviso Legal + emails) | ✅ |
| **3** | CRM Kanban en Streamlit + SQLite/Turso | ✅ |
| **3.1** | Perfiles de scrap configurables | ✅ |
| **3.2** | Lanzamiento de pipeline desde el CRM (local + cloud) | ✅ |

### Filtros de cualificación (Fase 1)

- Número de reseñas **> 20** (configurable por perfil).
- Puntuación **≥ 4.0** (configurable por perfil).
- Filtro de web: `required` (con web) / `none` (sin web) / `any`.

### Etapas del pipeline de ventas

`Nuevo` → `Contactado` → `Respuesta` → `Demo` → `Cerrado` · `Descartado`

---

## Bugs detectados

Auditoría del código actual. **Los cuatro están corregidos y verificados.**

| Bug | Qué provocaba | Estado |
| --- | ------------- | ------ |
| BUG-1 | El modo `enricher` no hacía nada en cloud | ✅ Validado en producción |
| BUG-2 | Una etapa inválida tumbaba la app entera | ✅ `tests/test_bug2.py` |
| BUG-3 | Se perdían 3 de 311 leads en cada import | ✅ `tests/test_bug3.py` |
| BUG-4 | Notas y etapas se sobrescribían entre leads | ✅ `tests/test_bug4.py` |
| RIESGO-A | Los logs públicos exponían nombres y emails | ✅ `tests/test_fase4_riesgos.py` |
| RIESGO-B | Los artifacts los descargaba cualquiera | ✅ `tests/test_fase4_riesgos.py` |
| RIESGO-D | Un scraping bloqueado terminaba en verde | ✅ `tests/test_fase4_riesgos.py` |

Los tests se ejecutan sobre una BD SQLite temporal y **no tocan Turso ni la BD local**:

```bash
for t in tests/test_*.py; do python "$t" || break; done
```

### ✅ BUG-1 · El modo `enricher` no funciona en cloud — **RESUELTO**

**Archivo:** `src/scraper/enricher.py` + `src/crm/db.py` · **Commit:** `f1fc0f2`

`enricher.run()` leía `data/leads_raw.json` del disco. En GitHub Actions el job arranca de un checkout limpio, donde ese fichero **no existe** (está en `.gitignore`). El modo `enricher` enriquecía cero leads y terminaba en verde, sin avisar.

**Fix aplicado:** regla de fuente de datos —**si existe el JSON, se usa; si no existe y hay Turso, se lee de la BD**—. Esto preserva el modo `pipeline` (donde el scraper acaba de escribir leads frescos que todavía no están en Turso) y arregla el modo `enricher` suelto. Añadidas `get_leads_to_enrich()` y `update_lead_enrichment()` en `db.py`. El guardado es **lead a lead**, para que una interrupción de Actions no pierda el trabajo hecho.

**Validado en producción:** run cloud sobre 31 leads pendientes → Director, Email y Sociedad rellenados. Ratio de acierto observado: **~90-95 % en email**, sensiblemente menor en director.

**Severidad:** Alta — funcionalidad anunciada en la UI que no hacía nada.

---

### ✅ BUG-2 · `ValueError` que tumba la app — **RESUELTO**

**Archivos:** `src/crm/app.py`, `src/crm/db.py`, `src/models/lead.py`

```python
index=PIPELINE_STAGES.index(lead["etapa"])
```

Si un lead tiene una `etapa` fuera de `PIPELINE_STAGES` (por ejemplo los valores legacy `Scraped` / `Enriched` que define `models/lead.py`, o una edición manual en la consola de Turso), `.index()` lanza `ValueError` y **rompe el render completo de la app**. Como Streamlit ejecuta el contenido de *todas* las pestañas en cada rerun, una sola fila mala deja la interfaz entera inaccesible — incluida la pestaña que necesitarías para arreglarla.

**Fix aplicado:**
1. `normalize_stage()` y `stage_index()` en `db.py`: cualquier valor nulo, vacío, con otras mayúsculas o desconocido cae en `Nuevo`. Se sustituyen los dos `.index()` directos de `app.py`.
2. `repair_invalid_stages()` se ejecuta dentro de `init_db()`: la BD **se auto-repara al arrancar**. Es idempotente, así que no consume escrituras si no hay nada roto.
3. `update_lead_stage()` e `import_leads()` normalizan antes de escribir, así que ya no es posible introducir una etapa inválida.
4. `models/lead.py` documenta que `estado` (`Scraped`/`Enriched`) describe el progreso del *scraping* y **no** es la etapa de venta.

**Efecto lateral positivo:** `import_leads()` ahora **respeta la etapa entrante si es válida** (antes forzaba `Nuevo`). Esto es lo que permitirá que la restauración de un backup de la Fase 6.8 conserve el pipeline en lugar de aplanarlo.

**Test:** `python tests/test_bug2.py` — 7 bloques, incluida la reproducción del crash original.

**Severidad:** Alta — provocaba caída total de la interfaz.

---

### ✅ BUG-3 · Criterio de deduplicación incoherente — **RESUELTO**

**Archivos:** `src/models/lead.py`, `src/crm/db.py`

| Punto | Clave de dedup (antes) |
| ----- | -------------- |
| `Lead.dedup_key` (scraper) | `nombre + direccion` |
| `import_leads()` (BD) | `nombre + ciudad` |

Una cadena con varias sedes en la misma ciudad (mismo nombre, distinta dirección) **pasaba el filtro del scraper pero se descartaba al importar**. Se perdían leads válidos de forma silenciosa.

**Medido sobre los datos reales del proyecto:** de 311 leads, **3 se perdían** en cada import (Clínicas Origen en Madrid y en Málaga, Somos Psicología en Madrid). Un ~1 % de fuga permanente y creciente conforme se amplían ciudades.

**Fix aplicado:**
1. `make_dedup_key()` en `models/lead.py`, **única fuente de verdad** para scraper y BD. Usa `nombre + direccion`, y recurre a `nombre + ciudad` solo si la dirección viene vacía (si no, todos los leads sin dirección colapsarían en una sola clave).
2. Normalización previa: se neutralizan mayúsculas, espacios dobles y **los glifos de icono del área de uso privado de Unicode** que Google Maps antepone a la dirección (`\ue0c8\n`). Sin esto la misma clínica generaba claves distintas entre ejecuciones.
3. Columna `dedup_key` en `leads` con **índice único parcial** (`WHERE dedup_key != ''`): la BD ya no admite duplicados ni por inserción manual. Es parcial para que una inserción a mano sin clave no reviente; el backfill se la calcula al arrancar.
4. `backfill_dedup_keys()` migra las BD existentes en una sola pasada. Al colapsar un duplicado conserva **la fila con más información útil** (notas > etapa avanzada > email directo > genérico > director), no la primera.
5. `import_leads()` deduplica también **dentro del propio lote** y descarta leads sin nombre.
6. Los textos se guardan ya limpios, así que la dirección deja de mostrarse con el glifo basura en la UI.

**Test:** `python tests/test_bug3.py` — 11 bloques, incluida una migración simulada de BD antigua y una importación real de los 311 leads.

**Severidad:** Media — pérdida silenciosa de leads cualificados.

---

### ✅ BUG-4 · Escritura en BD en cada rerun (notas) — **RESUELTO**

**Archivo:** `src/crm/app.py` (tabs Kanban y Detalle)

```python
if notas != (lead["notas"] or ""):
    update_lead_notes(lead["id"], notas)
```

Streamlit re-ejecuta el script entero en cada interacción. Como la comparación se hacía contra el valor cacheado (TTL 300 s), la condición seguía siendo verdadera tras guardar, disparando **un `UPDATE` por cada rerun**. En Turso eso es una petición HTTP por interacción.

**Medido con `streamlit.testing`:** tras editar una nota una sola vez y provocar 5 reruns, el código anterior hacía **6 escrituras**; el nuevo hace **1**.

**Bug adicional descubierto al escribir el test — corrupción de datos.** Los widgets del tab Detalle usaban claves **fijas** (`"detail_notas"`, `"detail_stage"`) en lugar de una por lead. Streamlit da prioridad a `session_state` sobre el parámetro `value=`, así que al cambiar de lead el recuadro conservaba el texto del anterior y lo **escribía sobre el lead nuevo**. Verificado ejecutando ambas versiones:

```
CÓDIGO VIEJO   Alfa: 'SECRETO DE ALFA'   Beta: 'SECRETO DE ALFA'   ← sobrescrito
CÓDIGO NUEVO   Alfa: 'SECRETO DE ALFA'   Beta: ''
```

Lo mismo ocurría con el selector de etapa: cambiar de lead podía mover al siguiente a la etapa del anterior. Es el bug más grave de los cuatro, porque **destruye trabajo manual en silencio** y no deja rastro.

**Fix aplicado:**
1. `on_change` con callbacks `_on_notes_change` / `_on_stage_change`: el guardado ocurre una sola vez, justo cuando el valor cambia, en lugar de en cada rerun.
2. Claves de widget **por lead** (`detail_notas_{id}`, `detail_stage_{id}`), lo que elimina la contaminación entre leads.
3. Se sustituye el `st.success` permanente por un `st.toast` que sólo aparece al guardar de verdad.

**Test:** `python tests/test_bug4.py` — 8 bloques que levantan la app real con `streamlit.testing.v1.AppTest` y cuentan las escrituras a BD.

**Severidad:** Alta (revisada al alza) — además del coste de cuota, sobrescribía notas y etapas entre leads.

---

## Riesgos y Sostenibilidad

> **Objetivo del proyecto: coste 0 € y autonomía indefinida.** Esta sección documenta qué puede
> romper esa premisa. Datos verificados en **agosto de 2026**; las cuotas de terceros cambian sin
> previo aviso, revisar cada 6 meses.

### Consumo real frente a cuota

Estimación con ~500 leads en BD y uso normal del CRM:

| Servicio | Cuota gratuita | Consumo estimado/mes | Margen usado |
| -------- | -------------- | -------------------- | ------------ |
| Turso · lecturas de fila | 500 M | ~0,5 M | **0,1 %** |
| Turso · escrituras de fila | 10 M | ~5 K | **0,05 %** |
| Turso · almacenamiento | 5 GB | < 10 MB | **0,2 %** |
| Turso · nº de bases de datos | 100 | 1 | — |
| GitHub Actions (repo **público**) | ilimitado | ~1.900 min | sin límite |
| Streamlit Community Cloud | 1 app privada | 1 app | — |
| Google Workspace | de pago (ya contratado) | ~900 emails | dentro de límites |

**Conclusión: ninguna cuota se agota.** El consumo no es el riesgo. Los riesgos son de
*política de proveedor*, *exposición de datos* y *fallo silencioso*.

---

### 🔴 Exposición de datos derivada del repositorio público

El repositorio es público, y eso tiene consecuencias que no son evidentes.

#### ✅ RIESGO-A · Los logs de Actions publican datos personales — **RESUELTO**

`maps_scraper.py` y `enricher.py` escribían en el log:

```python
log.info(f"  ✓ {nombre} | {rating}★ | {reviews} rev | {city}")
log.info(f"  ✓ {nombre} — dir={director} | email={email_directo}")
```

En un repositorio público **los logs de workflow son legibles por cualquiera, sin autenticarse**.
Se publicaban en internet nombres de clínicas, nombres de directores y sus emails: la base de datos
comercial regalada, y datos personales tratados sin control.

**Fix aplicado:** módulo `src/scraper/privacy.py` con dos helpers y un filtro de logging.

| Helper | En local | En CI |
| ------ | -------- | ----- |
| `mask(nombre)` | el nombre real | `<8fca98>` — hash corto y estable |
| `show(email)` | el email real | `sí` / `no` |

```
CI      ✓ <8fca98> — dir=sí | email=sí
LOCAL   ✓ Centro de Psicología Alameda — dir=María López | email=maria@alameda.es
```

El hash es **estable**, así que dos líneas del mismo lead siguen siendo correlacionables: se puede
depurar un run sin saber de quién se trata. En local no se oculta nada, que es donde los logs
sirven para algo.

Como red de seguridad, `RedactEmailsFilter` borra por expresión regular cualquier email del mensaje
ya formateado. Cubre lo que los helpers no pueden prever: el texto de una excepción de una
librería de terceros que arrastre una dirección. Se instala en los tres entry points.

#### ✅ RIESGO-B · Los artifacts son descargables por cualquiera — **RESUELTO**

`pipeline.yml` subía `leads_raw.json` y `leads_enriched.json` con 30 días de retención. La
documentación de GitHub exige *"read access to the repository"* para descargarlos — y en un
repositorio público **eso lo tiene todo el mundo**.

**Fix aplicado:** el paso de import decide si hacen falta y lo escribe en `GITHUB_OUTPUT`; la
subida queda condicionada a esa salida.

| Situación | ¿Se suben artifacts? | Motivo |
| --------- | -------------------- | ------ |
| `auto_import` activo y OK | **No** | Los datos ya están en Turso |
| `auto_import = 0` | Sí, 1 día | Es la única copia |
| El import a Turso falla | Sí, 1 día | Red de seguridad: mejor exponer que perder |

En los dos casos de excepción se emite un `::warning::` visible en la pestaña del run, y la
retención baja de 30 días a **1**. En la ruta normal —la del 95 % de los runs— ya no se publica
nada.

#### RIESGO-C · La app de Streamlit es pública por defecto

Sin configurar nada, cualquiera con la URL ve el CRM completo: leads, emails, directores y notas
comerciales.

**Fix (Fase 5):** `App Settings → Sharing → "Only specific people can view this app"`.

> ⚠️ El plan gratuito permite **una sola app privada a la vez**. Como solo hay una, encaja — pero
> queda ese cupo consumido.
>
> ⚠️ Al invitar a un visor, esa persona obtiene acceso a las analíticas de **todas** las apps
> públicas del workspace y puede invitar a más gente.

> Estas tres juntas son más graves de lo que parecen por separado: PsycoERP se vende con el
> argumento del cumplimiento LOPD/RGPD. Que el propio pipeline de captación filtre datos de
> contacto sería un problema comercial, no solo técnico.

---

### ⚠️ El repositorio público es *load-bearing*

Si el repositorio pasara a privado, **el mailer por sí solo agota el plan gratuito**:

```
12 ticks/hora × 7 h × 22 días laborables ≈ 1.850 ejecuciones/mes
GitHub factura redondeando al minuto      ≈ 1.850 min
Cuota gratuita en repositorio privado     =  2.000 min/mes
```

El 92 % de la cuota se consumiría **solo con los ticks**, sin contar el scraping (~120 min por
pasada). Con dos scrapings al mes ya habría que pagar.

**"Repositorio público" no es una elección estética: es lo que sostiene la gratuidad del proyecto.**

**Si algún día hiciera falta privacidad**, las salidas son: subir el intervalo a 20-30 min (menos
ticks), o mover mailer y scraper a un VPS propio (~10 €/mes, el mismo tipo de máquina que ya se
provisiona para los clientes, y sin límite de minutos).

---

### Riesgos de continuidad

| # | Riesgo | Prob. | Impacto | Mitigación |
| - | ------ | ----- | ------- | ---------- |
| **D** | **Google Maps sirve CAPTCHA a las IPs de Actions** | Alta | Scraper devuelve 0 leads en silencio | ✅ `ScraperBlockedError` aborta el run |
| **E** | **Cron desactivado a los 60 días sin actividad** | Alta | Mailer parado sin aviso | Job semanal de backup (= keepalive) |
| **F** | **Fallo silencioso del mailer** | Media | Semanas sin contactar a nadie | Heartbeat: alerta si 48 h sin envíos |
| **G** | Pérdida de la BD en Turso | Baja | Pérdida del `email_ledger` → riesgo de duplicar contactos | Backup semanal |
| **H** | Suspensión de la cuenta de Google por spam | Baja-Media | Se pierde el correo del negocio | Rampa + tope (ya en Fase 6) |
| **I** | Streamlit duerme la app a las 12 h sin tráfico | Alta | Arranque en frío al entrar | **No afecta al mailer** (corre en Actions) |

#### ✅ Sobre D — el más probable — **RESUELTO**

Los runners de GitHub usan IPs de datacenter de Azure, muy utilizadas por scrapers, y Google las
trata con desconfianza. El scraper podía empezar a devolver cero resultados **sin lanzar ningún
error**: `scroll_feed()` no encuentra el feed, registra un warning y continúa. El workflow
terminaba en verde habiendo extraído nada.

> Un job en verde que no hizo nada es peor que un job en rojo.

**Fix aplicado:** `scrape_city()` devuelve ahora `(leads, resultados_encontrados)`. Si el total de
resultados vistos en **todas** las ciudades es cero, `run()` lanza `ScraperBlockedError` y el
workflow termina en rojo.

La distinción importa: el criterio no es *"no se cualificó ningún lead"* —eso pasa legítimamente
con filtros estrictos o una ciudad ya agotada— sino *"Google no devolvió ni un solo resultado que
mirar"*, que solo ocurre si la búsqueda no funcionó. Basta con que **una** ciudad devuelva
resultados para que el run se considere sano.

El resumen final incluye `Resultados vistos: N`, para poder distinguir de un vistazo un filtro
demasiado estricto de un bloqueo.

#### Sobre E y F — el fallo silencioso es el enemigo real

El escenario malo no es que algo se rompa: es que **algo deje de funcionar sin avisar** y se
descubra tres semanas después que no se ha contactado a nadie.

Confirmado en la documentación de GitHub:

> *"In a public repository, scheduled workflows are automatically disabled when no repository
> activity has occurred in 60 days."*

**Solución: invertir la lógica del aviso.** Además del aviso por autonomía baja, añadir el
complementario — **si en 48 h laborables no se ha enviado ningún email estando el mailer activo,
avisar**. Una sola alerta detecta cron apagado, credencial caducada, cola vacía y cuenta suspendida.

#### Sobre I — Streamlit duerme rápido

Confirmado en la documentación actual: **todas las apps sin tráfico durante 12 horas se duermen**
(la política antigua de 7 días ya no aplica). Se despiertan solas al visitarlas.

**Es irrelevante para la autonomía**, y esto valida la decisión de arquitectura: el mailer vive en
GitHub Actions, no en Streamlit. Si el scheduler dependiera de la app, el sistema estaría muerto
cada mañana.

---

### Backup: hoy no existe

Si Turso desapareciera, se perdería todo: leads, notas comerciales, perfiles y —lo más caro de
reconstruir— el **`email_ledger`**. Sin él no se sabría a quién se ha contactado ya, y se
arriesgaría escribir dos veces a la misma clínica: justo la regla declarada inviolable.

**Propuesta — `.github/workflows/backup.yml` (Fase 6):**

- Cron semanal que exporta todas las tablas a JSON.
- Commit del export a un repositorio privado aparte (o artifact cifrado).
- Coste: ~30 s por semana.

> **Un solo job resuelve dos riesgos:** hace el backup **y**, al generar actividad semanal en el
> repositorio, **mantiene vivos los cron** (riesgo E).

---

### Nota de escalabilidad — `get_stats()`

`get_stats()` ejecuta **9 consultas `COUNT(*)` independientes**, cada una un escaneo completo de
la tabla. Con 5.000 leads son ~45.000 lecturas de fila por refresco de caché.

No es un bug y hoy es irrelevante (la caché de 300 s lo amortigua y el margen es del 0,1 %), pero
escala mal. Si algún día el volumen crece, sustituir por un único `GROUP BY etapa`.

---

### Verificado en agosto de 2026

| Dato | Estado |
| ---- | ------ |
| Turso free: 100 BD · 5 GB · 500 M lecturas · 10 M escrituras | ✅ Confirmado |
| Turso: endpoint `/v2/pipeline` vigente, sin deprecación | ✅ Confirmado |
| Turso: plataforma **no** está en sunset (libSQL + Turso Database conviven) | ✅ Confirmado |
| Turso: ¿borra o archiva BD inactivas? | ❓ **Sin confirmar** — no documentado. Preguntar a soporte |
| GitHub: cron desactivado a los 60 días sin actividad en repo público | ✅ Confirmado |
| GitHub: artifacts exigen "read access" → públicos en repo público | ✅ Confirmado |
| Streamlit: apps duermen a las **12 h** sin tráfico | ✅ Confirmado |
| Streamlit: 1 app privada en plan gratuito, con allowlist por email | ✅ Confirmado |
| Streamlit: ¿borrado automático por inactividad? | ❓ **Sin confirmar** — no documentado |

> Los dos puntos sin confirmar quedan cubiertos por el backup semanal: si Turso archivase la BD o
> Streamlit borrase la app, los datos seguirían existiendo fuera.

---

## Plan de Desarrollo

---

### Fase 4 — Corrección de bugs y exposición

Se ataca primero porque la Fase 5 refactoriza los mismos ficheros. Incluye el cierre de las
fugas de datos descritas en [Riesgos y sostenibilidad](#riesgos-y-sostenibilidad).

| Tarea | Ref. | Archivos |
| ----- | ---- | -------- |
| ~~Índice seguro de etapa + normalización en import~~ ✅ **hecho** | BUG-2 | `app.py`, `db.py`, `lead.py` |
| ~~Unificar clave de dedup a `nombre + direccion`~~ ✅ **hecho** | BUG-3 | `lead.py`, `db.py` |
| ~~Guardado explícito de notas~~ ✅ **hecho** | BUG-4 | `app.py` |
| ~~Enricher desde BD cuando hay Turso~~ ✅ **hecho** (`f1fc0f2`) | BUG-1 | `enricher.py`, `db.py` |
| ~~Calidad del lead basada en email, no en director~~ ✅ **hecho** | — | `app.py` |
| ~~**Sanear logs en CI**~~ ✅ **hecho** | RIESGO-A | `privacy.py`, `maps_scraper.py`, `enricher.py`, entry points |
| ~~**No subir artifacts si `auto_import` está activo**~~ ✅ **hecho** | RIESGO-B | `pipeline.yml` |
| ~~**Fallar el workflow si el scraper devuelve 0 leads**~~ ✅ **hecho** | RIESGO-D | `maps_scraper.py` |

**Test de validación:**
- ~~Insertar un lead con `etapa = "Scraped"` → la app no cae y el lead aparece en `Nuevo`.~~ ✅ **validado** (`python tests/test_bug2.py`)
- ~~Importar dos clínicas con mismo nombre y ciudad pero distinta dirección → entran las dos.~~ ✅ **validado** (`python tests/test_bug3.py`)
- ~~Editar notas y recargar → un solo `UPDATE`, el texto persiste.~~ ✅ **validado** (`python tests/test_bug4.py`)
- ~~Lanzar modo `enricher` en cloud → enriquece leads reales de Turso.~~ ✅ **validado**
- ~~Revisar el log público de un run → **no aparece ningún nombre, email ni director**.~~ ✅ **validado** (`python tests/test_fase4_riesgos.py`)
- ~~Forzar un scraping que no encuentre resultados → el workflow termina en **rojo**, no en verde.~~ ✅ **validado**

> **Fase 4 completada.** Los 4 bugs y los 3 riesgos de exposición están cerrados y cubiertos por
> tests. Falta únicamente confirmar RIESGO-A y RIESGO-B **en un run real** de Actions.

---

### Fase 5 — Refactor de UI + Guía rápida

Objetivo doble: **simplificar la interfaz** y añadir un **onboarding permanente** que sirva tanto de recordatorio tras semanas sin entrar como de guía para usuarios nuevos.

#### 5.1 · Refactor estructural

`src/crm/app.py` tiene ~700 líneas con todos los tabs en un único fichero. Se divide en:

```
src/crm/
├── app.py                # Solo layout, routing de tabs y bootstrap
├── db.py
├── pipeline_runner.py
├── turso_http.py
└── views/
    ├── guia.py           # NUEVO — Guía rápida + URLs
    ├── kanban.py
    ├── tabla.py
    ├── detalle.py
    ├── scrap.py
    └── emails.py         # NUEVO — Fase 6
```

Además:
- Extraer el CSS y los helpers repetidos (badges de calidad, formato de lead) a `views/_components.py`.
- Centralizar la invalidación de caché en un único helper.

#### 5.2 · Simplificación de la interfaz

Problemas actuales y solución propuesta:

| Problema | Solución |
| -------- | -------- |
| El tab Scrap mezcla estado de ejecución, perfiles y formulario en un scroll enorme | Separar en sub-secciones colapsables, con el estado de ejecución fijo arriba |
| Los filtros del Kanban y de la Tabla están duplicados y no comparten estado | Barra de filtros compartida en `session_state` |
| Mover de etapa exige abrir el expander y usar un selectbox | Botones de acción rápida en la tarjeta (`→ Contactado`, `→ Descartado`) |
| El sidebar acumula import, métricas y zona peligrosa | Reordenar: métricas arriba, import en medio, zona peligrosa colapsada |
| No hay feedback de qué significa cada icono de calidad | Leyenda en la Guía rápida + tooltips |

#### 5.3 · Guía rápida (nuevo tab `📖 Guía`)

Primer tab de la app, visible al entrar. Contenido:

**a) Flujo de trabajo en 4 pasos** — diagrama y explicación corta:

```
1. Configurar perfil  →  2. Lanzar scrap  →  3. Revisar leads  →  4. Activar envíos
```

**b) Chuleta de acciones frecuentes** — tabla de "quiero hacer X → dónde se hace".

**c) Glosario** — qué es un perfil de scrap, qué significa cada etapa, qué implica cada color de lead (🟢🟡🟠🔴), qué es "autonomía".

**d) Estado del sistema** — semáforo en vivo:
- ¿Hay pipeline corriendo?
- ¿Está el mailer activo?
- ¿Cuántos días de autonomía quedan?
- ¿Está la BD en local o en cloud?
- **¿Cuándo fue el último envío?** (detecta el cron apagado — ver riesgo E)
- **¿Cuándo fue el último backup?**

**e) 🔗 Enlaces importantes** — sección de URLs, que es donde vive todo lo que hoy se olvida:

| Recurso | Para qué |
| ------- | -------- |
| Dashboard de Turso | Ver/editar la BD cloud, sacar credenciales |
| App en Streamlit Cloud | La URL del CRM |
| Secrets de Streamlit | Donde se configuran `TURSO_*`, `GITHUB_*`, SMTP |
| **Sharing de Streamlit** | **Restringir quién puede ver el CRM** (ver RIESGO-C) |
| GitHub Actions del repo | Ver ejecuciones, logs y artifacts |
| Secrets de GitHub | Donde se configuran los secrets de CI |
| Admin de Google Workspace | Gestión del correo, DKIM, App Passwords |
| Contraseñas de aplicación de Google | Generar/revocar la credencial SMTP |
| Web de PsycoERP | La landing del producto |

> Las URLs se guardan en una tabla `app_links` editable desde la propia UI, no hardcodeadas. Así se pueden añadir recursos sin tocar código.

**f) ⚠️ Recordatorios de mantenimiento** — lo que se olvida y rompe el sistema:

- **El repositorio debe seguir siendo público** — es lo que sostiene la gratuidad ([por qué](#️-el-repositorio-público-es-load-bearing)).
- **Los cron se desactivan a los 60 días sin actividad** — el job de backup semanal lo evita, pero conviene saberlo.
- Revisar cuotas de terceros cada 6 meses.

**Test de validación:** entrar en la app sin contexto previo y ser capaz de lanzar un scrap y activar los envíos usando **solo** la guía.

---

### Fase 6 — Módulo de envío de emails

Sistema de contacto en frío automatizado, con ritmo humano y garantía de **un único impacto por clínica**.

#### Reglas de negocio (inamovibles)

| Regla | Implementación |
| ----- | -------------- |
| **1 email por dominio, jamás repetido** | Índice único sobre dominio normalizado en `email_ledger` |
| Se prefiere el email directo al genérico | Prioridad `email_directo` > `email_generico` |
| Solo de **lunes a viernes, 08:00-15:00** hora española | Validación con `zoneinfo` sobre `Europe/Madrid` |
| Intervalo **aleatorio de 5-15 min** entre envíos | `next_send_at` persistido en BD |
| Tope diario con **rampa de calentamiento** | Calculado desde `warmup_start_date` |
| Pie de baja en todos los mensajes | Plantilla obligatoria |

---

#### 6.0 · Configuración externa (checklist manual) ⚠️ BLOQUEANTE

**Nada de esto es código.** Hay que hacerlo antes de empezar la Fase 6.

##### ✅ 1. Activar Verificación en 2 pasos

Obligatorio: Google retiró en 2024 el acceso SMTP con usuario+contraseña. Las contraseñas de aplicación **son una función del 2FA** — sin él, la opción ni aparece.

```
myaccount.google.com  →  Seguridad  →  Verificación en 2 pasos  →  Activar
```

##### ✅ 2. Generar la contraseña de aplicación

Cuenta: `info@psycoerp.es` (**cuenta real de Workspace**, confirmado — la credencial se genera sobre esta misma cuenta).

```
myaccount.google.com  →  Seguridad  →  Verificación en 2 pasos
   →  Contraseñas de aplicaciones  →  Crear  →  nombre: "PsycoLead Mailer"
```

Resultado: 16 caracteres. **Se guarda solo en secrets, nunca en la BD ni en el repo** (el repositorio es público).

##### ✅ 3. Verificar SPF, DKIM y DMARC

Se envía desde el dominio con el que también se factura: si se quema la reputación, se quema el negocio.

> ⚠️ **DKIM en Google Workspace NO viene activado por defecto.** Tener SPF no implica tener DKIM. Hay que generar la clave en `admin.google.com → Apps → Google Workspace → Gmail → Autenticar correo` y publicar el TXT resultante.

Comandos de verificación:

```bash
# SPF — debe incluir include:_spf.google.com
dig +short TXT psycoerp.es | grep spf

# DKIM — debe devolver una clave pública (v=DKIM1; k=rsa; p=...)
dig +short TXT google._domainkey.psycoerp.es

# DMARC — debe existir al menos con p=none
dig +short TXT _dmarc.psycoerp.es
```

| Registro | Valor esperado |
| -------- | -------------- |
| SPF | `v=spf1 include:_spf.google.com ~all` |
| DKIM | `v=DKIM1; k=rsa; p=MIIBIjANBg...` |
| DMARC | `v=DMARC1; p=none; rua=mailto:...` (subir a `quarantine` más adelante) |

##### ✅ 4. Recursos gráficos

- [ ] **PNG del logo a ≥160 px de ancho** (se muestra a 80 px; el doble es para pantallas retina).
      El `favicon.png` actual es demasiado pequeño y se verá borroso.
      *Solo necesario si más adelante se quiere firma con logo — la firma del envío automático no lleva imagen.*

##### ✅ 5. Secrets a configurar

| Secret | Local (`.streamlit/secrets.toml`) | Cloud (Streamlit + GitHub) |
| ------ | --------------------------------- | -------------------------- |
| `SMTP_HOST` | `smtp.gmail.com` | ídem |
| `SMTP_PORT` | `587` | ídem |
| `SMTP_USER` | `info@psycoerp.es` | ídem |
| `SMTP_APP_PASSWORD` | 16 caracteres de Google | ídem |
| `EMAIL_FROM_NAME` | `Info \| PsycoERP` | ídem |

---

#### 6.1 · Esquema de datos

Nuevas tablas en `db.py` (compatibles SQLite + Turso):

```sql
-- Registro histórico: la garantía de "1 solo impacto por dominio"
CREATE TABLE email_ledger (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dominio      TEXT NOT NULL,          -- normalizado: minúsculas, sin www
    email        TEXT NOT NULL,
    lead_id      INTEGER,
    enviado_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX idx_ledger_dominio ON email_ledger(dominio);

-- Cola de envío
CREATE TABLE email_queue (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id       INTEGER NOT NULL,
    destinatario  TEXT NOT NULL,
    dominio       TEXT NOT NULL,
    asunto        TEXT NOT NULL,
    cuerpo_texto  TEXT NOT NULL,
    cuerpo_html   TEXT NOT NULL,
    estado        TEXT DEFAULT 'pending',  -- pending|sending|sent|failed|skipped
    intentos      INTEGER DEFAULT 0,
    error         TEXT DEFAULT '',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at       TIMESTAMP
);

-- Plantillas editables desde el CRM
CREATE TABLE email_templates (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre   TEXT NOT NULL,
    asunto   TEXT NOT NULL,       -- admite {nombre}, {ciudad} (ver nota sobre {director})
    cuerpo   TEXT NOT NULL,
    activa   INTEGER DEFAULT 0
);

-- Exclusiones: bajas, rebotes, competencia, clientes actuales
CREATE TABLE email_suppression (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    dominio    TEXT NOT NULL,
    email      TEXT DEFAULT '',
    motivo     TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX idx_suppression_dominio ON email_suppression(dominio);

-- Configuración clave/valor del mailer
CREATE TABLE email_settings (
    clave  TEXT PRIMARY KEY,
    valor  TEXT
);

-- Auditoría de cada intento
CREATE TABLE email_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_id   INTEGER,
    evento     TEXT,       -- claimed|sent|failed|skipped|window_closed|cap_reached
    detalle    TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Claves de `email_settings`:**

| Clave | Default | Descripción |
| ----- | ------- | ----------- |
| `activo` | `0` | Interruptor maestro del mailer |
| `warmup_start_date` | — | Fecha de inicio de la rampa |
| `tope_maximo` | `45` | Techo tras el calentamiento |
| `tope_manual` | vacío | Si tiene valor, ignora la rampa |
| `intervalo_min_min` | `5` | Minutos mínimos entre envíos |
| `intervalo_max_min` | `15` | Minutos máximos entre envíos |
| `ventana_inicio` | `8` | Hora de inicio (Europe/Madrid) |
| `ventana_fin` | `15` | Hora de fin (Europe/Madrid) |
| `next_send_at` | — | Timestamp del próximo envío permitido |
| `firma_html` | — | Firma en HTML |
| `firma_texto` | — | Firma en texto plano |
| `aviso_emails` | `dacormus@gmail.com,dacormo01@hotmail.com` | Destinatarios de alertas |
| `aviso_umbral_dias` | `3` | Días de autonomía que disparan el aviso |
| `aviso_ultimo` | — | Cooldown de 24 h entre avisos |

> **Nota:** teléfono, firma y correos de aviso viven en BD, **no en el código**. El repositorio es público.

---

#### 6.2 · Motor de envío (`src/mailer/`)

```
src/mailer/
├── sender.py       # Construcción MIME + envío SMTP
├── queue.py        # Encolado, claim atómico, supresión
├── scheduler.py    # Ventana horaria, jitter, tope diario
├── templates.py    # Renderizado de plantillas y firma
└── autonomy.py     # Cálculo de stock y avisos
```

##### Claim atómico (crítico)

`TursoConnection.commit()` es un *no-op*: cada sentencia se auto-confirma y **no hay transacciones**. Un `SELECT` seguido de `UPDATE` permitiría que dos ticks solapados enviaran el mismo email. Se resuelve con una única sentencia:

```sql
UPDATE email_queue
   SET estado = 'sending', intentos = intentos + 1
 WHERE id = (SELECT id FROM email_queue
              WHERE estado = 'pending'
              ORDER BY id LIMIT 1)
   AND estado = 'pending';
```

Después se lee qué fila quedó en `sending`. Idéntico en SQLite y Turso.

##### Orden de operaciones al enviar

```
1. ¿mailer activo?                       no → salir
2. ¿ventana horaria abierta (L-V 8-15)?  no → salir
3. ¿now >= next_send_at?                 no → salir
4. ¿enviados_hoy < tope_diario?          no → salir + log
5. Claim atómico de 1 email de la cola
6. Re-check: dominio en ledger o supresión → marcar 'skipped', salir
7. INSERT en email_ledger                ← ANTES de enviar
8. smtplib.send()
9. Marcar 'sent', mover lead a 'Contactado'
10. next_send_at = now + random(5,15) min
```

> **Asimetría deliberada:** el registro en `email_ledger` se escribe **antes** del envío. Si el envío falla a mitad, se pierde un email — pero **nunca se duplica**. Es la garantía dura de la regla "una sola llamada a la puerta".

##### Construcción del mensaje

- `multipart/alternative` con versión **texto plano + HTML** (solo-HTML penaliza en filtros antispam).
- Cabecera `From` con `email.utils.formataddr(("Info | PsycoERP", "info@psycoerp.es"))`.
- `Reply-To` a la misma dirección.
- Conexión `smtp.gmail.com:587` con STARTTLS.

##### Firma del envío automático

Deliberadamente **sobria y sin logo**: en un primer contacto frío, una firma con imágenes y tablas parece envío masivo y resta credibilidad. Lleva color e iconos para no quedar plana, pero mantiene aspecto de escrita a mano.

**HTML:**

```html
<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#333;line-height:1.6">
  <div style="color:#999">—</div>
  <div style="font-weight:bold;color:#0B3075;font-size:14px">David Guerrero</div>
  <div style="color:#555;font-size:12px;margin-bottom:4px">Fundador &amp; CTO · PsycoERP</div>
  <div style="font-size:12px;color:#444">
    🌐 <a href="https://psycoerp.es" style="color:#0B3075;text-decoration:none;font-weight:bold">psycoerp.es</a>
    &nbsp;·&nbsp; 📞 +34 642 963 419
  </div>
</div>
```

**Texto plano:**

```
—
David Guerrero
Fundador & CTO · PsycoERP
🌐 psycoerp.es · 📞 +34 642 963 419
```

> La firma completa con logo se sigue usando **manualmente desde Gmail** en las respuestas. La firma configurada en la interfaz de Gmail **no viaja por SMTP** — solo se aplica al redactar desde el cliente web. Por eso hay que replicarla aquí.

##### Pie de baja (obligatorio en todas las plantillas)

```
Te escribo porque encontré los datos de contacto de tu clínica en su web.
Si no quieres recibir nada más, responde "BAJA" y no volveré a escribirte.
```

Cubre el art. 22 LSSI (medio sencillo y gratuito de oposición) y el art. 14 RGPD (informar del origen de los datos). Además **mejora la entregabilidad**: los filtros penalizan el correo comercial sin vía de salida.

---

#### 6.3 · Scheduler

##### Entry point único

```bash
python run_mailer.py --tick          # Procesa como máximo 1 envío y sale
python run_mailer.py --status        # Muestra estado sin enviar
python run_mailer.py --daemon        # Bucle local (equivalente al cron)
```

`--tick` es **idempotente y sin estado propio**: todo el estado vive en BD. El mismo comando sirve para el cron de Actions, el cron local y el botón "Enviar 1 ahora" del CRM.

##### Workflow `.github/workflows/mailer.yml`

```yaml
on:
  schedule:
    - cron: "*/5 5-14 * * 1-5"   # Ventana amplia en UTC
  workflow_dispatch:

concurrency:
  group: mailer                  # Impide runs solapados
  cancel-in-progress: false
```

**Por qué la ventana UTC es más amplia que la real:** el cron de Actions es UTC y España cambia de huso dos veces al año. Se define un rango amplio y **es el script quien decide** con `zoneinfo("Europe/Madrid")` si son las 08:00-15:00 locales. El horario de verano se resuelve solo, para siempre.

##### Limitaciones asumidas de GitHub Actions

| Limitación | Impacto | Mitigación |
| ---------- | ------- | ---------- |
| Granularidad mínima de 5 min | Los huecos caen en múltiplos de 5 | El retraso irregular de Actions añade ruido natural |
| Retrasos de 5-20 min en horas punta | El ritmo se vuelve más irregular | Es *deseable*: parece más humano |
| **Los cron se desactivan tras 60 días sin commits** | El mailer se para en silencio | Job keepalive o recordatorio en la Guía rápida |
| Runs solapados | Envío duplicado | `concurrency: group` + claim atómico |

> Repositorio **público** → minutos de Actions ilimitados. Cada tick dura ~30 s.

##### Rampa de calentamiento

Se calcula sola, sin intervención manual:

| Días desde `warmup_start_date` | Tope diario |
| ------------------------------ | ----------- |
| 0-2   | 10 |
| 3-6   | 15 |
| 7-13  | 25 |
| 14-20 | 35 |
| 21+   | `tope_maximo` (45) |

**Freno automático:** si la tasa de fallos SMTP de los últimos 7 días supera el 5 %, la rampa se congela y se avisa.

> ⚠️ **Límite conocido:** al haber descartado IMAP, solo se detectan los rechazos **síncronos** (5xx en el momento del envío). Los rebotes diferidos que llegan a la bandeja no se ven. Se mitiga con validación de dominio previa al encolado.

##### Nota de capacidad

La ventana 08:00-15:00 son 420 minutos. Con un hueco medio de 10 min salen **~42 emails/día**, que es el techo de lo prudente incluso en Workspace. Por eso el **tope diario es el freno maestro**: el intervalo define el *ritmo*, el tope define el *volumen*. Son dos controles independientes.

---

#### 6.4 · UI del mailer (nuevo tab `📧 Emails`)

**a) Panel de control**
- Interruptor maestro ON/OFF, bien visible.
- Estado: `Activo · Día 9 de calentamiento · tope hoy 25 · enviados hoy 12 · próximo a las 11:47`.
- Botón "Enviar 1 ahora" para pruebas manuales.

**b) Cola de envío**
- Tabla con destinatario, clínica, estado, intentos.
- Acciones: quitar de la cola, mover a supresión, reintentar fallidos.

**c) Plantillas**
- Editor de asunto y cuerpo con variables `{nombre}` y `{ciudad}`.
- **Vista previa renderizada con un lead real**, incluida la firma.
- Validación: bloquear el guardado si falta el pie de baja.

> ⚠️ **`{director}` no se usa en el envío automático.** Medido en producción, el enricher
> acierta el email en un ~90-95 % pero el director bastante menos, y en algunos casos devuelve
> el propio nombre de la clínica como si fuera una persona. Un email en frío que empieza
> con el nombre equivocado —o con el nombre del negocio usado como nombre propio— destruye
> la credibilidad más de lo que la personalización la aporta. El copy automático se dirige
> siempre a la **clínica** (`{nombre}`, dato 100 % fiable desde Google Maps).
>
> El campo `director` **se conserva** en la BD: es útil en el seguimiento manual, cuando alguien
> responde y quieres saber con quién hablas, o para buscar a la persona en LinkedIn.
> Si en el futuro se añade una plantilla con `{director}`, el motor debe **excluir** de esa
> plantilla los leads donde `director` esté vacío o coincida con `nombre`.

**d) Encolado**
- Selector de leads por ciudad, perfil de origen o calidad.
- Muestra **cuántos se encolarían realmente** tras aplicar ledger, supresión y validación de dominio.

**e) Configuración**
- Ventana horaria, intervalos, tope máximo, firma, correos de aviso.

**f) Historial**
- Últimos envíos con fecha, destinatario y resultado.

---

#### 6.5 · Panel de Autonomía

Responde a la pregunta operativa clave: **"¿cuándo me quedo sin contactos y dónde tengo que scrapear?"**

```
📬 Contactables ahora:      127
📤 Ritmo actual:             25/día
⏳ Autonomía:                5 días   (se agota el martes 26)

Desglose por ciudad:
  Madrid      ▓▓▓▓▓▓▓▓░░   62 disponibles
  Barcelona   ▓▓▓░░░░░░░   18 disponibles
  Valencia    ░░░░░░░░░░    0  ← agotada
  Bilbao      ░░░░░░░░░░    0  ← agotada
```

**Definición de "contactable":**

```
leads con email válido
  − dominios ya en email_ledger
  − dominios en email_suppression
  − dominios que no resuelven
```

`autonomía_días = contactables / tope_diario_actual`

**Desglose por ciudad y por `perfil_origen`** (ya existente en el modelo): indica **exactamente dónde scrapear** — si Valencia y Bilbao están secas, toca abrir Sevilla o bajar el filtro de reseñas.

##### Aviso proactivo por email

Cuando la autonomía baja de `aviso_umbral_dias` (3 por defecto), el propio tick envía un aviso a:

- `dacormus@gmail.com`
- `dacormo01@hotmail.com`

> ⚠️ Hotmail/Outlook filtra con dureza. Marcar `info@psycoerp.es` como remitente seguro en esa cuenta o los avisos acabarán en la papelera.

Con **cooldown de 24 h** (`aviso_ultimo`) para no recibir un aviso por tick.

Contenido: días restantes, contactables totales y **lista de ciudades agotadas**.

##### Heartbeat — aviso de fallo silencioso

El aviso anterior cubre "me quedo sin contactos". Falta el complementario, que es el que de verdad
protege la autonomía:

> **Si el mailer está activo y han pasado 48 h laborables sin ningún envío → avisar.**

Una sola alerta detecta cuatro fallos distintos que de otro modo pasarían desapercibidos durante
semanas:

| Síntoma | Causa real |
| ------- | ---------- |
| No se envía nada | Cron desactivado a los 60 días (riesgo E) |
| No se envía nada | App Password revocada o caducada |
| No se envía nada | Cola vacía y sin leads contactables |
| No se envía nada | Cuenta de Google suspendida |

Se implementa comparando `MAX(sent_at)` de `email_ledger` contra la hora actual, dentro del propio
tick. Mismo cooldown de 24 h y mismos destinatarios.

> ⚠️ **Límite conocido:** si el fallo es que el cron está apagado, el tick no se ejecuta y por tanto
> **no puede avisar de sí mismo**. Por eso el job semanal de backup es la red de seguridad real: al
> generar actividad mantiene los cron vivos, y su propio fallo sí es visible en la pestaña Actions.

---

#### 6.6 · Entorno de pruebas local ⚠️ OBLIGATORIO ANTES DE PRODUCCIÓN

Todo debe validarse en local antes de tocar una sola dirección real.

##### Modos de prueba (variables de entorno)

| Variable | Efecto |
| -------- | ------ |
| `EMAIL_DRY_RUN=1` | **No envía nada.** Escribe cada mensaje en `data/emails_out/*.eml` y registra en `email_log`. Permite abrir el `.eml` y ver el render exacto |
| `EMAIL_REDIRECT_TO=dacormus@gmail.com` | Envía de verdad, pero **redirige todos los destinatarios** a esa dirección. El destinatario original se conserva en una cabecera `X-Original-To` |
| `EMAIL_FAST_CLOCK=1` | Ignora la ventana horaria y usa intervalos **en segundos** en lugar de minutos. Permite simular un día entero en minutos |
| `EMAIL_FORCE_WINDOW=1` | Ignora solo la restricción L-V 08:00-15:00 |

##### Seed de datos de prueba

```bash
python run_mailer.py --seed-test
```

Crea leads ficticios con dominios controlados por el usuario y varios casos límite:
- Clínica con email directo **y** genérico → debe elegir el directo.
- Dos clínicas del **mismo dominio** → solo debe salir un email.
- Clínica con dominio inexistente → debe descartarse al encolar.
- Clínica ya presente en `email_suppression` → debe saltarse.

##### Checklist de validación

- [ ] `--dry-run` genera `.eml` correctos, con firma bien renderizada en Gmail y Outlook.
- [ ] La versión texto plano se ve bien (probar con imágenes desactivadas).
- [ ] **Dedup por dominio:** dos leads del mismo dominio → un solo envío.
- [ ] **Prioridad de email:** con `info@` y `direccion@` se elige `direccion@`.
- [ ] **Tope diario:** con tope 3, el cuarto tick no envía y registra `cap_reached`.
- [ ] **Ventana horaria:** fuera de L-V 08:00-15:00 no envía y registra `window_closed`.
- [ ] **Jitter:** los intervalos varían entre el mínimo y el máximo configurados.
- [ ] **Concurrencia:** dos ticks en paralelo no envían el mismo email.
- [ ] **Supresión:** un dominio en `email_suppression` nunca se envía.
- [ ] **Transición de etapa:** tras enviar, el lead pasa a `Contactado`.
- [ ] **Autonomía:** el cálculo cuadra con el número real de contactables.
- [ ] **Aviso:** al bajar del umbral llegan los dos correos, y no se repiten en 24 h.
- [ ] **Redirect:** con `EMAIL_REDIRECT_TO` todo llega a la dirección propia.
- [ ] **Rampa:** cambiando `warmup_start_date` el tope evoluciona según la tabla.

##### Prueba de humo en producción

1. Activar con `tope_manual = 2` durante un día.
2. Verificar en Gmail → "Mostrar original" que **SPF, DKIM y DMARC pasan**.
3. Comprobar que no cae en spam (probar contra una cuenta Gmail y otra Outlook propias).
4. Solo entonces iniciar la rampa de calentamiento.

---

#### 6.7 · Contenido del mensaje

Se elabora aparte, con criterios de copywriting outbound B2B:

- **Asunto corto y sin gancho comercial evidente** (los asuntos tipo "oferta" se filtran).
- **Primera línea personalizada** con datos reales del lead (nombre de la clínica, ciudad).
- **Problema antes que producto:** hablar de reparto de salas y comisiones, no de "ERP".
- **Ángulo financiero:** pago único frente a suscripción eterna.
- **CTA de baja fricción:** pedir permiso para enviar el vídeo, no pedir una reunión.
- **Longitud:** por debajo de 150 palabras.
- **Sin enlaces en el primer contacto** salvo el dominio propio (los enlaces suben el riesgo de spam).

---

#### 6.8 · Backup y keepalive

Un único workflow que resuelve dos riesgos a la vez (**G** pérdida de datos y **E** cron
desactivado).

**`.github/workflows/backup.yml`**

```yaml
on:
  schedule:
    - cron: "0 3 * * 0"    # Domingos a las 03:00 UTC
  workflow_dispatch:
```

**Qué hace:**

1. Exporta todas las tablas de Turso a JSON (`leads`, `email_ledger`, `email_suppression`,
   `email_settings`, `email_templates`, `scrap_profiles`, `app_links`).
2. Sube el export **cifrado** o lo commitea a un repositorio privado aparte.
3. Registra la fecha en `email_settings` para mostrarla en la Guía rápida.

**Por qué también es keepalive:** GitHub desactiva los cron de repositorios públicos tras 60 días
sin actividad. Un job semanal —y su commit asociado— garantiza que eso no ocurra nunca.

> ⚠️ **El export NO puede subirse al repositorio público**: contiene emails, directores y notas
> comerciales. Repositorio privado separado o artifact cifrado, nunca `git commit` aquí.

**Prioridad de restauración.** Si hubiera que reconstruir desde cero, el orden importa:

| Tabla | Criticidad | Motivo |
| ----- | ---------- | ------ |
| `email_ledger` | 🔴 **Máxima** | Sin ella se duplicarían contactos — rompe la regla inviolable |
| `email_suppression` | 🔴 Máxima | Se escribiría a quien pidió la baja |
| `leads` (notas y etapas) | 🟡 Alta | Recuperable re-scrapeando, pero se pierde el trabajo comercial |
| `scrap_profiles`, `app_links` | 🟢 Baja | Se reconfiguran en minutos |

**Test de validación:** borrar la BD local, restaurar desde el último backup y comprobar que
`email_ledger` queda íntegro.

---

### Fase 7 — Backlog documentado (no se implementa)

| Feature | Motivo del aplazamiento |
| ------- | ----------------------- |
| **Reposición automática de leads** | El tick detecta autonomía baja y dispara solo el scraper vía GH API (`pipeline_runner` ya sabe hacerlo). Aplazado: primero hay que confiar en el sistema manualmente |
| Tracking de aperturas y clicks | ❌ Descartado. Requiere endpoint HTTP público; Streamlit no sirve |
| Detección de respuestas vía IMAP | ❌ Descartado por ahora. Sería un segundo tick con `imaplib` |
| Secuencias de seguimiento (follow-ups) | Incompatible con la regla "1 solo impacto" |
| Integración con Hunter.io | Fallback de emails cuando la extracción web falla |
| Export a Notion / Airtable | — |
| Dashboard de conversión | Métricas por ciudad, perfil y plantilla |

---

## Orden de Trabajo

```
Fase 4 (Bugs + fugas de datos) → Test
   → Fase 5 (UI + Guía) → Test
      → Fase 6.0 (Config externa) ⚠️ BLOQUEANTE
         → Fase 6.1-6.3 (Datos + Motor + Scheduler) → Test local
            → Fase 6.4-6.5 (UI + Autonomía + Heartbeat) → Test
               → Fase 6.6 (Validación local completa) ⚠️ OBLIGATORIO
                  → Fase 6.8 (Backup + keepalive) ⚠️ ANTES DE PRODUCCIÓN
                     → Prueba de humo en producción (tope 2/día)
                        → Rampa de calentamiento
```

> Cada fase se desarrolla, se testea y se avanza. **Nada de avanzar sin validar.**
> En la Fase 6 esta regla no es una buena práctica: es la diferencia entre tener un canal de captación o perder la cuenta de correo del negocio.

> **El backup (6.8) va antes de producción, no después.** En cuanto se envíe el primer email real,
> el `email_ledger` pasa a ser el activo más valioso y menos reconstruible del sistema.

---

## Decisiones de diseño tomadas

Registro de las decisiones acordadas y su motivo.

| Decisión | Elección | Motivo |
| -------- | -------- | ------ |
| Unidad de deduplicación | **Dominio**, no dirección | "Se llama una sola vez a la puerta de cada empresa", aunque tenga 50 buzones |
| Email preferido | `email_directo` > `email_generico` | Llega a quien tiene criterio de decisión |
| Momento de registro en ledger | **Antes** del envío | Preferible perder un email a duplicarlo |
| Zona horaria | Cron UTC amplio + decisión en Python | Inmune al cambio de horario de verano |
| Estrategia de scheduler | Tick sin estado cada 5 min | Reanudable; alternativa con `sleep` de 6 h es frágil y excede el límite de job |
| Tope diario | Rampa automática en BD | Evita el baneo sin gestión manual |
| Firma del envío automático | Reducida, sin logo | Una firma con imágenes en frío parece envío masivo |
| Firma completa con logo | Solo manual desde Gmail | Las respuestas se escriben a mano |
| Almacenamiento de firma y teléfono | En BD, no en código | El repositorio es público |
| Autenticación SMTP | App Password + 2FA | Google retiró el acceso básico; OAuth2 es desproporcionado y el relay exige IP fija |
| Aviso de stock bajo | Email a dos direcciones propias | No exige entrar en la app para enterarse |
| Reposición automática | Aplazada a Fase 7 | Primero hay que ver el comportamiento del sistema |
| Pie de baja | Obligatorio | Art. 22 LSSI + mejora la entregabilidad |
| Personalización del copy | Nombre de la **clínica**, no del director | El director tiene baja fiabilidad y a veces duplica el nombre del negocio |
| Campo `director` | Se conserva, pero solo para uso manual | Útil al responder o buscar en LinkedIn; no apto para automatizar |
| Tracking y IMAP | Descartados | Exigen infraestructura fuera del alcance |
| **Visibilidad del repositorio** | **Público, de forma permanente** | En privado el mailer solo consume el 92 % de la cuota gratuita de Actions |
| Datos personales en logs y artifacts | Prohibidos en CI | En repo público son legibles por cualquiera |
| Backup y keepalive | Un único job semanal | Resuelve pérdida de datos y cron desactivado a la vez |
| Ubicación del scheduler | GitHub Actions, nunca Streamlit | Las apps de Community Cloud duermen a las 12 h sin tráfico |
| Destino del backup | Repo privado o artifact cifrado | El export contiene datos personales |

---

## Comandos

Ver [`context/How_To.md`](context/How_To.md) para el detalle completo.

```bash
source venv/bin/activate

# Scraping y enriquecimiento
python run_scraper.py  --headless --cities Madrid,Barcelona
python run_enricher.py --headless --limit 20
python run_pipeline.py --headless

# CRM
streamlit run src/crm/app.py        # http://localhost:8501

# Mailer (Fase 6)
EMAIL_DRY_RUN=1 python run_mailer.py --tick
python run_mailer.py --status
```
