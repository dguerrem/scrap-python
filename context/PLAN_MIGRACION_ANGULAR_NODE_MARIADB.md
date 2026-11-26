# Plan maestro de migración — PsycoLead CRM

> **Documento de transferencia para GPT6-Luna.** Especifica el objetivo, el análisis del sistema existente, las decisiones recomendadas, las fases, los invariantes y los criterios de aceptación. No equivale a autorización para migrar datos reales ni para activar envíos. Implementar por fases, verificando el estado real antes de cada cambio.
>
> **Fecha del análisis:** 20 de noviembre de 2026  
> **Repositorio analizado:** `scrap-python`  
> **Objetivo de producto:** sustituir Streamlit/Turso/GitHub como dependencias operativas por una aplicación autoalojada en el VPS del usuario, conservando el funcionamiento del CRM y el pipeline.

---

## 0. Instrucciones operativas para GPT6-Luna

1. Lee este documento completo y después inspecciona el código/documentación actual citado en «Fuentes del análisis». El código y el estado de producción pueden haber cambiado desde este análisis.
2. **Antes de implementar una fase**, entrega un breve plan de archivos, cambios, riesgos, migración de datos y pruebas. Si los hallazgos contradicen este documento, informa de la diferencia y actualiza la propuesta; no inventes que la realidad coincide con el plan.
3. No intentes reescribir todo el repositorio en una sola tarea. Mantén el sistema antiguo operativo hasta superar los criterios de aceptación de la fase correspondiente.
4. No leas, copies, publiques ni modifiques datos de producción, secretos, `.env`, `data/crm.db`, WAL/SHM ni exportaciones reales salvo instrucción explícita del usuario. Desarrolla con fixtures sintéticos y una MariaDB local vacía.
5. No actives tareas programadas de envío ni ejecutes envíos reales durante desarrollo. Los modos de prueba actuales también pueden reservar el dominio en el ledger; compruébalo antes de cualquier prueba.
6. No habilites simultáneamente dos mailers, dos importadores/escritores ni dos schedulers contra la misma base de datos. En el corte debe haber un único sistema que pueda enviar y un único origen de escritura.
7. Conserva el idioma español de la UI, las decisiones de producto y las reglas de negocio documentadas. No elimines una función porque no tenga una API evidente: rastrea su flujo completo.
8. Cada cambio funcional necesita tests automatizados, logs sin datos personales y una forma documentada de desplegar y revertir. No cambies semánticas críticas silenciosamente.
9. **GPT6-Luna empezará en un repositorio nuevo y no tendrá acceso a este proyecto legado.** Este MD transmite decisiones y requisitos, pero no contiene la implementación completa del scraper ni el contenido exacto de cada vista. Antes de portar, solicitar/importar el «Paquete de código legado necesario» de la sección 10. Sin esos archivos, no afirmar que el scraper o la paridad están implementados.
10. Priorizar UX/UI en cada entrega: presentar pronto una aplicación navegable y recoger feedback. El producto debe ser genérico por nicho, excluir el Kanban antiguo y ofrecer tema claro/oscuro desde el MVP.

---

## 1. Resumen ejecutivo y decisión de stack

### Decisión recomendada

- **Frontend:** Angular + TypeScript, como SPA compilada y servida estáticamente por Nginx.
- **Backend principal:** Node.js LTS vigente al empezar la implementación + TypeScript + NestJS con adaptador Fastify. Modular monolith, API REST versionada y módulos separados por dominio.
- **Persistencia:** MariaDB en el VPS, InnoDB, `utf8mb4`, migraciones SQL versionadas, pool de conexiones y SQL parametrizado. Usar transacciones explícitas para operaciones que lo requieran y constraints únicos como última defensa. No confiar en que un ORM traduzca las operaciones críticas correctamente.
- **Scraper y enricher iniciales:** conservarlos en Python y Playwright, ejecutados como worker aislado. Node.js coordina trabajos y es el único propietario de la lógica de escritura de la base de datos. La integración prevista es mediante API interna autenticada y resultados por lotes; no exponer el worker a Internet.
- **Mailer:** mantener el mailer Python actual como único emisor hasta que el equivalente Node esté probado. Después portar la lógica a un worker Node/TypeScript y hacer un corte controlado. Si el port presenta un riesgo desproporcionado, el mailer Python puede permanecer temporalmente como worker; lo no negociable es una sola instancia activa y una sola base de datos autoritativa.
- **Ejecución/operación:** servicios gestionados por systemd o Docker Compose (elegir tras revisar el VPS), proxy HTTPS, MariaDB accesible solo localmente/red privada, secretos fuera del repositorio y backups cifrados fuera del VPS con restauraciones verificadas.

### Por qué Node, no Java

El producto es un CRM de una persona/equipo pequeño con una interfaz web y trabajos de fondo, no un servicio Java existente que necesite conservar compatibilidad. TypeScript comparte tipos y convenciones con Angular, simplifica el despliegue y ofrece suficiente capacidad para consultas CRM, colas, SMTP y coordinación del scraper. Java es viable, pero no aporta una ventaja demostrada para este perfil que compense introducir otro lenguaje y ecosistema. **No se debe escoger Java salvo que un requisito real aparezca durante el diseño.**

### Por qué Angular, no Astro para el CRM

El CRM tiene filtros con estado, edición de leads, tabla, operaciones de email y seguimiento de trabajos. Es una aplicación interactiva; Angular encaja directamente. Astro destaca en sitios de contenido y páginas mayormente estáticas. Puede llamar a una API Node, pero no sustituye al backend ni al scheduler; añadir Astro y una aplicación de estado interactiva introduciría dos modelos de frontend sin resolver una necesidad actual. Si en el futuro se necesita una web comercial, Astro puede ser un proyecto/página separado, no la base del CRM. El Kanban de la UI heredada se excluye expresamente.

### Python no es un requisito técnico permanente

Playwright tiene bindings oficiales para Python y Node.js. Por tanto, **no es obligatorio** permanecer en Python para hacer scraping. Sin embargo, el scraper y el enricher existentes ya están implementados y conectados al pipeline. Migrarlos ahora sería reescribir lógica de navegador, selectores, scroll, extracción, filtros y fallos sin una ganancia de rendimiento garantizada. El trabajo dominante es navegación/red/esperas del navegador; cambiar el lenguaje no hace automáticamente más rápido Google Maps. La opción de menor riesgo y coste es mantener Python para esos workers y migrarlos solo si una medición y una necesidad operacional lo justifican.

### Producto genérico por nicho y UX/UI prioritario

El proyecto nuevo será un CRM y gestor de scraping configurable para distintos nichos. El sector original solo explica la procedencia de algunos datos; **no es una restricción ni debe aparecer en la experiencia nueva**.

- No mostrar en títulos, textos, onboarding, ejemplos, valores por defecto, mensajes, documentación dentro de la app ni seeds referencias a clínicas de psicología, PsycoERP, su precio, pacientes o un sector fijo.
- Usar vocabulario neutral según corresponda: «negocio», «empresa», «lead», «contacto», «persona responsable», «nicho» y «perfil de búsqueda».
- Permitir configurar nicho, consulta de búsqueda, ubicación y filtros. No fijar una plantilla sectorial. Si se admiten variables, el scraper debe soportar explícitamente `{niche}` y `{city}` y la interfaz debe previsualizar la consulta resuelta.
- Presentar los campos heredados `director` y `sociedad` como «Persona responsable» y «Razón social», o definir un mapping genérico equivalente; no perder sus datos históricos.
- Incluir **modo claro**, **modo oscuro** y **seguir preferencia del sistema**. Persistir la opción; evitar el flash de tema incorrecto al arrancar. Revisar contraste WCAG, foco de teclado, responsive y estados hover/disabled/error en ambos temas.
- **Excluir el módulo Kanban**: no diseñar ni migrar su tab, componentes o navegación. Conservar `etapa` y sus valores en BD si los requieren el detalle, la tabla, el mailer o los registros históricos; excluir la vista no autoriza a borrar datos.
- UX/UI prima sobre la fidelidad visual de Streamlit: crear una interfaz consistente, ligera y usable en escritorio/móvil. Entregar primero un prototipo navegable de las vistas principales y ajustar con feedback del usuario antes de dar por cerrados los estilos.

---

## 2. Qué resuelve actualmente el sistema

PsycoLead es el sistema interno de prospección de PsycoERP. No es solo un tablero: combina extracción, normalización, CRM, operación de correo, programación, privacidad y recuperación de datos.

### Flujo funcional actual

1. Se configura un perfil de búsqueda: nombre, query, ciudades, mínimo de reseñas, puntuación, política de web, scrolls y `auto_import`.
2. Google Maps se procesa con Playwright desde `run_scraper.py`/`run_pipeline.py`; se limpia y deduplica cada lead.
3. El enricher visita webs y extrae datos de contacto y sociedad desde páginas públicas, incluyendo Aviso Legal, mediante `run_enricher.py`.
4. Los resultados se escriben en JSON/CSV (`data/leads_raw.*`, `data/leads_enriched.*` y `data/runs/{run_id}-...`). Según el modo de ejecución, se importan al CRM.
5. El CRM permite consultar/filtrar leads, actualizar su etapa y notas, ver ficha, exportar/importar datos, administrar perfiles y lanzar o consultar ejecuciones.
6. El mailer permite administrar plantillas, cola, límites, horarios, actividad, supresiones, ledger e historial. Encola manualmente leads y procesa como máximo un envío por tick.
7. El backup actual exporta tablas, cifra el resultado con GPG y lo conserva como artifact de GitHub Actions.

### UI que debe conservarse

La navegación actual tiene seis secciones, pero el producto nuevo **no debe replicarlas literalmente**. Debe comprobarse cada detalle en `src/crm/views/` y conservar las funciones útiles, aplicando las decisiones explícitas de producto:

- **Guía:** puede conservarse como onboarding breve y genérico, solo si aporta valor. No copiar sin rediseño el texto sectorial heredado.
- **Kanban:** eliminado por decisión del usuario; no forma parte del producto nuevo.
- **Tabla:** listado, filtros, datos y exportación; importación manual y acción peligrosa de vaciar leads con confirmación.
- **Detalle:** ficha y edición de lead/notas/etapa.
- **Emails:** estado del mailer, plantillas, cola, encolado, ledger/historial, supresión, ajustes, pruebas y controles existentes.
- **Scrap:** perfiles, lanzamiento de `scraper`/`enricher`/`pipeline`, estado, log e historial disponible.

Además de estas vistas, migrar la barra de filtros/contadores, los flujos de importación de JSON y los estados de carga/error. La UI actual no debe tratarse como especificación suficiente: verificar el comportamiento en cada vista.

#### Cambios visuales obligatorios solicitados para el producto nuevo

Usar `src/crm/views/guia.py` como referencia para identificar el contenido antiguo que se debe retirar, no como diseño a copiar:

1. **Texto genérico:** eliminar cualquier texto que diga o presuponga «clínicas de psicología», PsycoERP, un precio, pacientes o un nicho predeterminado. Reemplazar por onboarding y ejemplos neutrales y editables.
2. **Estado del sistema de la Guía:** eliminar la métrica **«Cerrados»**. Quitar de esa sección las filas/tarjetas **«Base de datos / Turso (cloud)»**, **«Robot de scraping»** y **«Envío automático»**, incluyendo estados como «Los cambios los ve todo el mundo», «Terminó bien», «Encendido», contadores de cola y métricas de envíos. No exponer detalles de Turso ni automatización de correo en la Guía. Si hacen falta comprobaciones de salud para operar, ubicarlas en un panel técnico/admin privado y mostrar solo estado útil, neutro y no sensible.
3. **Secciones eliminadas de la Guía:** no recrear **«Qué significa cada cosa»**, **«Enlaces importantes»** ni **«Cosas que no puedes olvidar»**. No copiar sus seeds/contenido. Si se conserva Guía, limitarla a instrucciones de uso actuales, breves, genéricas y útiles.
4. **Kanban:** sacar del menú, rutas Angular, componentes, navegación por teclado y documentación visible del producto. No renderizar columnas de etapas ni drag-and-drop. Mantener el campo de etapa comercial y las acciones que sigan teniendo uso en tabla/detalle/email.
5. **Tema visual:** el selector claro/oscuro/sistema debe estar accesible de forma evidente, conservarse entre sesiones y aplicarse a todas las páginas/componentes, incluidos formularios, tablas, diálogos, estados de carga y errores.

### Modos de ejecución del pipeline

`src/crm/pipeline_runner.py` maneja modos `scraper`, `enricher` y `pipeline`. En local lanza subprocesos y guarda estado/log en archivos; en cloud dispara GitHub Actions vía API. El workflow actual `.github/workflows/pipeline.yml` es `workflow_dispatch` (no tiene `schedule` en el YAML actual), acepta modo/perfil/ciudades, y puede importar a Turso. Los JSON/CSV de `data/runs` son parte del historial operativo y no deben perderse sin decidir una política de retención.

---

## 3. Hallazgos técnicos del repositorio actual

### Componentes y fuentes principales

| Dominio | Fuentes actuales | Papel que cumplen |
|---|---|---|
| Entidad y deduplicación | `src/models/lead.py` | `Lead`, limpieza Unicode y clave normalizada por nombre+dirección, o nombre+ciudad si falta dirección. |
| BD y CRUD | `src/crm/db.py` (793 líneas) | Inicializa esquema, selecciona SQLite o Turso por entorno, migraciones incrementales, importación, dedup, leads, perfiles, enlaces y mailer. Es el principal punto de acoplamiento al reemplazar. |
| Cliente Turso | `src/crm/turso_http.py` | Implementa cliente HTTP libSQL y emulación de cursor SQLite; `commit()` no da transacciones reales. No se debe trasladar esta abstracción sin necesidad a MariaDB. |
| CRM | `src/crm/app.py`, `src/crm/views/*.py`, `src/crm/views/_components.py` | Navegación, vistas, filtros, formularios, caché y callbacks de Streamlit. Se reimplementan en Angular/API. |
| Lanzador de pipeline | `src/crm/pipeline_runner.py` | Ejecuta localmente subprocess o inicia/consulta workflow en GitHub. Estado local actual usa archivos y PID; no es una cola durable adecuada para el nuevo sistema. |
| Scrap | `src/scraper/maps_scraper.py`, `src/scraper/config.py`, `run_scraper.py` | Playwright, configuración de provincias/localidades, queries, filtros, esperas y outputs. Preservar primero. |
| Enrichment | `src/scraper/enricher.py`, `run_enricher.py` | Completa email/director/sociedad visitando webs y puede leer leads desde BD en modo cloud. Preservar primero. |
| Mailer | `src/mailer/{config,store,templates,sender,scheduler,autonomy}.py`, `run_mailer.py` | Configuración SMTP, acceso SQL, plantillas, envío, scheduler, límites, opt-outs, autonomía, CLI y pruebas. Portar solo con pruebas de paridad estrictas. |
| Backup | `run_backup.py`, `.github/workflows/backup.yml` | Exporta los datos actuales, cifra backup y programa su ejecución mediante GitHub Actions. Debe sustituirse por backup propio del VPS con copia externa. |
| Pruebas | `tests/test_*.py` | Incluyen bugs de etapa/dedup/persistencia/paridad SQLite-Turso, privacidad, riesgos y más de 60 comprobaciones del mailer. Son especificación de comportamiento, no se descartan al abandonar Turso. |

### Esquema de BD legado conocido (SQLite/Turso)

Este inventario representa el esquema construido por `src/crm/db.py`, incluyendo las columnas e índices añadidos en `init_db()` y `_init_mailer_schema()`. Los tipos son los de SQLite/libSQL; no son todavía el DDL MariaDB. El orden/valores reales deben verificarse contra la fuente de producción al iniciar Fase 0.

#### Tablas CRM

| Tabla | Columnas y tipos/defaults legados | Restricciones/índices conocidos |
|---|---|---|
| `leads` | `id INTEGER PRIMARY KEY AUTOINCREMENT`; `nombre TEXT NOT NULL`; `ciudad TEXT NOT NULL DEFAULT ''`; `direccion TEXT DEFAULT ''`; `telefono TEXT DEFAULT ''`; `url TEXT DEFAULT ''`; `puntuacion REAL DEFAULT 0.0`; `resenas INTEGER DEFAULT 0`; `director TEXT DEFAULT ''`; `email_directo TEXT DEFAULT ''`; `email_generico TEXT DEFAULT ''`; `sociedad TEXT DEFAULT ''`; `etapa TEXT DEFAULT 'Nuevo'`; `notas TEXT DEFAULT ''`; `perfil_origen TEXT DEFAULT ''`; `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`; `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`; migración añade `dedup_key TEXT DEFAULT ''`. | `idx_leads_dedup_key` único parcial sobre `dedup_key` cuando no es cadena vacía. `idx_leads_etapa_puntuacion` en `(etapa, puntuacion DESC, resenas DESC)`. El import/backfill repara etapas legacy y dedup keys; auditar el código completo y BD real antes del DDL destino. |
| `scrap_profiles` | `id INTEGER PRIMARY KEY AUTOINCREMENT`; `nombre TEXT NOT NULL`; `search_query TEXT DEFAULT 'Clínica de psicología en {city}'` (default heredado sectorial: **no reutilizar**, cambiar a consulta genérica vacía o editable); `ciudades TEXT DEFAULT '[]'` (JSON serializado); `min_reviews INTEGER DEFAULT 20`; `min_rating REAL DEFAULT 4.0`; `require_website TEXT DEFAULT 'required'` (valores de UI a comprobar: `required`/`none`/`any`); `max_scrolls INTEGER DEFAULT 20`; `auto_import INTEGER DEFAULT 1`; `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`. | No se declara constraint de unicidad para el nombre del perfil en el esquema conocido. La configuración objetivo debe incluir el nicho y permitir queries/filtros configurables; definir migración de perfil legado y no inferir un nicho para datos antiguos. |
| `app_links` | `id INTEGER PRIMARY KEY AUTOINCREMENT`; `categoria TEXT DEFAULT 'General'`; `titulo TEXT NOT NULL`; `url TEXT NOT NULL`; `para_que TEXT DEFAULT ''`; `orden INTEGER DEFAULT 100`. | Seeds existentes vienen de contenido de producto antiguo. No copiar automáticamente enlaces/textos de la Guía que el usuario pidió eliminar. |

#### Tablas del mailer legado

| Tabla | Columnas y tipos/defaults legados | Restricciones/índices conocidos |
|---|---|---|
| `email_ledger` | `id INTEGER PRIMARY KEY AUTOINCREMENT`; `dominio TEXT NOT NULL`; `email TEXT NOT NULL`; `lead_id INTEGER`; `enviado_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`. | `idx_ledger_dominio` único sobre `dominio`. En este código `dominio` puede representar la clave única: dominio corporativo normalizado o email completo para proveedor público. |
| `email_queue` | `id INTEGER PRIMARY KEY AUTOINCREMENT`; `lead_id INTEGER NOT NULL`; `destinatario TEXT NOT NULL`; `dominio TEXT NOT NULL`; `asunto TEXT NOT NULL`; `cuerpo_texto TEXT NOT NULL`; `cuerpo_html TEXT NOT NULL`; `estado TEXT DEFAULT 'pending'`; `intentos INTEGER DEFAULT 0`; `error TEXT DEFAULT ''`; `claim_token TEXT DEFAULT ''` (también migrado); `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`; `claimed_at TIMESTAMP`; `sent_at TIMESTAMP`. | `idx_queue_estado` sobre `estado`. `idx_queue_pendiente` único parcial sobre `dominio` mientras `estado IN ('pending','sending')`. `claim()` actual usa actualización atómica con token; `liberar_atascados()` recupera claims antiguos con menos de 3 intentos. |
| `email_templates` | `id INTEGER PRIMARY KEY AUTOINCREMENT`; `nombre TEXT NOT NULL`; `asunto TEXT NOT NULL`; `cuerpo TEXT NOT NULL`; `activa INTEGER DEFAULT 0`. | No hay constraint conocido que garantice una sola plantilla activa; el código la activa con dos sentencias. Diseñar garantía/transacción destino. |
| `email_suppression` | `id INTEGER PRIMARY KEY AUTOINCREMENT`; `dominio TEXT NOT NULL`; `email TEXT DEFAULT ''`; `motivo TEXT DEFAULT ''`; `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`. | `idx_suppression_dominio` único sobre `dominio`. La tabla es una protección y se debe preservar. |
| `email_settings` | `clave TEXT PRIMARY KEY`; `valor TEXT`. | Valores sembrados por `_MAILER_DEFAULTS`: `activo='0'`; `warmup_start_date=''`; `tope_maximo='45'`; `tope_manual=''`; `intervalo_min_min='5'`; `intervalo_max_min='15'`; `ventana_inicio='8'`; `ventana_fin='15'`; `next_send_at=''`; `firma_html=''`; `firma_texto=''`; `aviso_emails=''`; `aviso_umbral_dias='3'`; `aviso_ultimo=''`; `heartbeat_ultimo=''`; `ultimo_backup=''`. Los settings activos pueden diferir de estos defaults y deben capturarse en Fase 0. |
| `email_log` | `id INTEGER PRIMARY KEY AUTOINCREMENT`; `queue_id INTEGER`; `evento TEXT`; `detalle TEXT`; `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`. | No se declara FK en el DDL conocido. Revisar política de retención y datos personales antes de migrar `detalle`. |

#### Tablas que no existen todavía en el esquema legado

`pipeline_runs`/tabla de jobs durables y, opcionalmente, usuarios/sesiones son **nuevas propuestas**, no tablas que se puedan exportar desde la BD actual. Como mínimo, definir tabla de jobs con: ID/`run_id` único, modo (`scraper`/`enricher`/`pipeline`), nicho, perfil y snapshot de parámetros, estado (`queued`/`running`/`completed`/`failed`/`cancelled`), timestamps UTC, progreso/contadores, lease/heartbeat, cancelación solicitada, error sanitizado y referencia privada a outputs. GPT6-Luna debe diseñar DDL/migración para MariaDB; no presentar esta propuesta como esquema existente.

El DDL legado conocido no declara claves foráneas explícitas. Revisar todas las operaciones de borrado y retención antes de añadir FKs/cascadas: no permitir que borrar un lead borre accidentalmente ledger, supresiones, cola o trazabilidad. Tampoco se conoce si la BD de producción coincide con SQLite local. En Fase 0 obtener `SHOW CREATE TABLE`, índices, columnas, recuentos y consistencia de IDs de la fuente confirmada; no abrir ni modificar `data/crm.db` por defecto.

Para el **esquema objetivo multi-nicho**, decidir e implementar explícitamente:

- Un catálogo/valor `nicho` en perfiles y un vínculo o snapshot de nicho en cada lead/run, para filtrar los datos por categoría aun si el perfil se renombra o elimina.
- Si deduplicar es global por negocio (clave actual) o por nicho+negocio. No añadir nicho a `dedup_key` automáticamente: puede crear duplicados de la misma empresa al buscarla en nichos distintos. Documentar la decisión y probar ambos escenarios.
- Consulta por defecto vacía/neutra y ejemplos editables; no importar el default sectorial histórico de `scrap_profiles.search_query`.
- Labels de UI genéricos para los datos heredados. Si se renombra una columna en MariaDB, mantener el mapping de export/import antiguo y verificar el enriquecedor antes de retirar los nombres originales.

### Invariantes de datos y negocio

- `Lead.estado` (`Scraped`/`Enriched`) y `leads.etapa` (`Nuevo`, `Contactado`, `Respuesta`, `Demo`, `Cerrado`, `Descartado`) representan conceptos distintos. No colapsarlos.
- `dedup_key` normaliza el texto insensible a mayúsculas y neutraliza caracteres Unicode de control/formato/uso privado que aparecen en Maps. Conserva sedes distintas por dirección; sin dirección utiliza ciudad.
- Las filas de lead con notas o etapas avanzadas valen más que duplicados simples: la lógica de repair/backfill existente conserva la fila más rica. Evitar importaciones que sobrescriban notas/etapa por datos frescos del scraper.
- El mailer selecciona el email directo antes que el genérico cuando corresponde; la disponibilidad del email no equivale a autorización de envío.
- La clave de contacto no siempre es un dominio literal: para proveedores públicos (p. ej. Gmail/Outlook) el código usa el email completo; para dominios corporativos usa el dominio normalizado sin `www.`. La columna `dominio` puede contener esa clave según el flujo. Portar la función exacta de `src/mailer/store.py`; cubrir dominios genéricos, espacios, mayúsculas, `www.` y emails malformados.
- El ledger se escribe **antes** del SMTP. Se prefiere perder un mensaje ante una caída a duplicar el contacto. Una respuesta SMTP ambigua no se debe reintentar automáticamente sin revisar la reserva.
- Las bajas/supresiones y el ledger se conservan en migración. No limpiar/recrear esas tablas para «empezar de cero».
- La cola tiene estados `pending`, `sending`, `sent`, `failed`, `skipped`, contador de intentos y recuperación de claims atascados. No reducirla a una lista de correos.
- El `dry-run` actual pasa por la lógica de tick y puede dejar una reserva en el ledger y marcar la cola como procesada; no asumir que es un simulador inocuo. Definir explícitamente el comportamiento del nuevo modo antes de probarlo.

### Operación y diferencias documentales que hay que resolver

Hay indicios de más de un estado operativo y documentos no sincronizados. **No inferir producción a partir del YAML o de un MD; confirmar en el VPS/GitHub con el usuario antes del corte.**

- `context/VPS_MAILER.md` documenta un `psycolead-mailer.timer` systemd en el VPS, que usa Turso, y advierte que no debe convivir con GitHub Actions.
- `.github/workflows/mailer.yml` todavía incluye un `schedule` y `workflow_dispatch`. El documento VPS dice que ese workflow fue deshabilitado, pero el fichero versionado muestra su configuración. Confirmar si el workflow está deshabilitado realmente y si el timer corre antes de tocar nada.
- `context/VPS_MAILER.md` describe ventana 08:00–19:00, mientras `_MAILER_DEFAULTS`/`scheduler.py` dan por defecto 08:00–15:00. El valor real está en BD y puede ser distinto. Capturar settings activos y aprobados; no fijar defaults suponiendo que representan producción.
- `.github/workflows/pipeline.yml` actual solo tiene `workflow_dispatch`; `context/github-actions-plan.md` contiene ideas antiguas sobre schedule/funciones futuras. Separar hechos vigentes de backlog.
- El workflow de backup de GitHub exporta datos de Turso y los cifra, mientras el objetivo nuevo debe respaldar MariaDB y ficheros privados del VPS. No conservar GitHub como único backup del sistema autoalojado.
- `context/session-handoff.md` advierte que una contraseña SMTP aparecida en conversación debe rotarse. No copiar credenciales de documentación o historial; revisar/rotar secretos durante preparación del VPS.

---

## 4. Arquitectura destino propuesta

```text
Navegador
   │ HTTPS
   ▼
Nginx (TLS, Angular estático, reverse proxy /api)
   │                         ┌──────────────────────────────┐
   ├── /api ────────────────▶│ Node.js + TypeScript         │
   │                         │ API REST modular             │
   │                         │ auth, CRM, perfiles, runs,    │
   │                         │ import/export, email admin    │
   │                         └──────────────┬───────────────┘
   │                                        │ SQL parametrizado
   │                         ┌──────────────▼───────────────┐
   │                         │ MariaDB / InnoDB              │
   │                         │ VPS, no puerto público         │
   │                         └──────────────▲───────────────┘
   │                                        │ API interna y lotes
   │                         ┌──────────────┴───────────────┐
   │                         │ Worker Python + Playwright    │
   │                         │ scraper / enricher             │
   │                         │ privado, jobs durables          │
   │                         └──────────────────────────────┘
   │
   └── UI de inicio, leads (tabla/detalle), scrap/perfiles, ajustes y emails

Worker Node separado del API (mismo código/módulos): scheduler de mail,
SMTP, reclamación de cola, recuperación y trabajos de mantenimiento.
```

### Límites de responsabilidad

- **Angular:** presentación y validación de UX; no conecta directamente con MariaDB ni contiene secretos. Implementa tema claro/oscuro/sistema y navegación sin Kanban.
- **Node API:** autentica y autoriza; contiene reglas de CRM y mailer, valida todos los inputs, aplica paginación, transacciones y auditoría; único escritor del esquema de aplicación.
- **Worker Node:** ejecución persistente del mailer y jobs programados. No depender de timers dentro de cada instancia HTTP, que podrían duplicarse al reiniciar/escalar.
- **Worker Python:** usa el Playwright existente y comunica progreso/resultados a endpoints internos autenticados. Node valida e importa resultados por lotes idempotentes. El worker no expone una API pública ni recibe instrucciones arbitrarias de shell desde la web.
- **MariaDB:** una sola base activa del nuevo sistema. La app y workers usan usuario de BD con privilegios mínimos; administración desde localhost/socket o canal privado.
- **Ficheros de ejecución:** almacenar JSON/CSV/logs necesarios bajo directorio privado y permisos restringidos, con retención configurable. No servir directamente artefactos sensibles desde rutas públicas ni subirlos a artifacts públicos.

### Trabajos de scraping durables

El actual PID/archivo de estado y el workflow GitHub no proporcionan una cola del VPS. Para el objetivo propio, registrar cada run en BD (ID único, modo, perfil/snapshot de parámetros, estado, timestamps, progreso, contadores, error sanitizado y ubicación protegida de outputs). La API crea/cancela/consulta trabajos; el worker Python reclama un trabajo con lease, envía heartbeat/progreso y carga resultados en lotes idempotentes. Incluir expiración/recuperación de lease y cancelación cooperativa. Solo permitir perfiles y modos conocidos: no convertir el panel en ejecución arbitraria de comandos.

### Experiencia de desarrollo local y comandos sencillos (requisito)

El usuario desarrolla en macOS y quiere personalizar su experiencia con comandos breves y predecibles. GPT6-Luna debe incluir desde el primer esqueleto un CLI/wrapper documentado (`./dev.sh` o equivalente portable; comandos npm y Docker Compose por debajo) y mantenerlo estable. El criterio principal es que **una orden levante el CRM en localhost junto con el worker de scraping local**, y que el CRM use ese worker, no GitHub Actions, Turso ni un servicio remoto.

Contrato de comandos propuesto (se pueden ajustar nombres durante el diseño, pero se deben cubrir todas estas operaciones):

```bash
# Primera preparación: instala/valida dependencias, genera .env.local seguro,
# arranca MariaDB local vacía y aplica migraciones; no carga datos reales.
./dev.sh setup

# Configuración guiada de puertos, rutas y servicios locales.
./dev.sh config

# Inicia la aplicación de desarrollo completa: MariaDB, API Node, Angular y
# servicio/worker Python+Playwright local. Deja logs y estado accesibles.
./dev.sh up
# Abrir http://localhost:4200 (o el puerto único que se documente).
# Angular llama a la API local; la API solo llama al worker local configurado.

# Ver estado y logs por componente.
./dev.sh status
./dev.sh logs [web|api|scraper|db]
./dev.sh open

# Ejecuta un trabajo de scraping en el servicio LOCAL, con un perfil/nicho
# elegido y datos de desarrollo. Requiere confirmación si se conecta a Internet.
./dev.sh scrape --profile "Mi perfil de prueba"

# Ejecuta suites/checks sin tocar servicios ni datos productivos.
./dev.sh test

# Detiene servicios conservando la BD local.
./dev.sh down

# Borra solo el entorno/BD sintética local tras advertir y confirmar.
./dev.sh reset
```

Requisitos de funcionamiento:

- `./dev.sh up` debe arrancar stack local repetible: UI, API Node, MariaDB de desarrollo y worker/scraper Python+Playwright. La primera ejecución instala o construye lo necesario y deja instrucciones claras si falta Docker/Node/Python/Chromium. Ninguna orden puede conectarse a producción por defecto.
- Configurar explícitamente una URL interna de worker local en el entorno de desarrollo, por ejemplo `SCRAPER_SERVICE_URL=http://127.0.0.1:<puerto>` si los procesos se ejecutan directamente, o un hostname de Compose equivalente si se ejecutan en contenedores. Documentar cuál se usa; no mezclar los dos modelos.
- Camino de la petición: navegador localhost → API Node localhost → servicio local Python. El navegador no se conecta a MariaDB ni invoca directamente una URL externa de scraper. El API y worker validan/limitan el job.
- Si el servicio local no está arriba/no responde, el API devuelve error visible «servicio local de scraping no disponible» y el panel ofrece cómo iniciarlo. **No hacer fallback silencioso a GitHub Actions, Turso, Streamlit ni otro VPS.**
- El perfil de búsqueda debe poder editarse/seleccionarse en UI y por CLI; permitir indicar nicho, query, ubicación(es) y filtros sin valores sectoriales fijos. Registrar el snapshot del perfil en cada run.
- Separar explícitamente `scrape` real (hace solicitudes a sitios) de tests/dry-run sintéticos. Las pruebas no deben hacer scraping ni reservar ledgers reales. Mostrar confirmación antes de lanzar una ejecución que navegue sitios externos.
- `status`, `logs`, `test`, `down` y `setup` no deben lanzar scraping ni email. `reset` debe requerir una confirmación reforzada y solo actuar sobre el contenedor/volumen local de desarrollo.
- Proveer `.env.example` sin secretos y `.env.local`/equivalente ignorado por Git; `setup` no debe sobrescribir valores del usuario sin confirmación. Permitir cambiar puertos, perfil de navegador, rutas de datos, servicios activos y URL del worker fácilmente. `./dev.sh config` ofrece una configuración guiada o indica qué variables editar; también se aceptan overrides por flags/env sin editar código.
- Incluir aliases package scripts equivalentes (`dev`, `dev:api`, `dev:web`, `dev:scraper`, `test`, `lint`, `build`) para quien prefiera usar npm directamente; mantener una opción simple de un solo comando como camino recomendado.

### Ruta guiada para GPT6-Luna: repositorio nuevo → MVP

El usuario abrirá un proyecto nuevo desde cero y adjuntará este MD. GPT6-Luna debe seguir este orden y no asumir acceso al repo viejo:

1. **Orientación y límites.** Leer este documento; explicar en pocas líneas el stack recomendado y el orden de trabajo. Confirmar que no hay código legado accesible. No pedir secretos ni datos reales. Si falta el paquete legado, pedirlo y mientras tanto avanzar con arquitectura, UX, scaffold y fixtures únicamente.
2. **Recibir artefactos fuente.** Pedir que se adjunten los archivos listados en «Paquete de código legado necesario», evitando `data/`, `.env`, secrets, dumps con leads, `.git` y credenciales. Revisar scraper/enricher/DB/mailer/tests para levantar el contrato de funciones y localizar dependencias específicas. No recrear el scraper desde una descripción textual si se solicita paridad exacta.
3. **Proponer plan de ejecución.** Antes de generar muchos archivos, devolver una checklist por etapas con estructura de carpetas, versiones, comandos, decisiones de persistencia, local worker, riesgos y pruebas. Registrar incertidumbres en `docs/decisions/` y solicitar decisión solo para bloqueos reales.
4. **Crear base del repo.** Inicializar repo privado hasta revisar política de datos; estructura monorepo sencilla; Node/TypeScript API y worker, Angular web, worker Python Playwright, MariaDB dev, migraciones, Compose/wrapper de comandos, lockfiles, `.gitignore`, `.env.example`, README y CI local. No copiar DB ni archivos de datos del legado.
5. **Hacer arrancable la experiencia local.** Implementar `./dev.sh setup`, `./dev.sh up`, `status`, `logs`, `down`, `test`; comprobar con servicios limpios y documentar URLs/puertos. Verificar que Node realmente se conecta a la URL local del worker y falla en modo seguro si no está. Esta verificación es un gate antes del desarrollo de scraping/UI.
6. **Definir diseño UX antes de funciones completas.** Presentar arquitectura de navegación y wireframe/mockup navegable en español. Menú mínimo propuesto: Inicio/resumen útil, Leads (tabla/detalle), Scraping/perfiles y, más adelante, Emails/Configuración. No incluir Kanban. Excluir las secciones de Guía y estados de sistema prohibidas. Implementar los tres modos de tema y validar contraste/teclado/responsive; pedir feedback visual temprano.
7. **Crear contratos y base MariaDB.** Especificar entidades, DDL MariaDB, migraciones y tests con datos falsos; definir el mapping de columnas sectoriales heredadas (`director` → persona responsable; etc.), el campo nicho y la deduplicación. No migrar datos reales en MVP. Asegurar auth básica antes de servir fuera de localhost.
8. **Implementar primer vertical slice.** Desde una pantalla, crear/seleccionar perfil genérico, mandar job al API local, que lo envía al worker Python local, observar estado/progreso, recibir resultados, persistirlos en MariaDB local y verlos en una tabla/ficha con búsqueda/filtros básicos. Debe funcionar de punta a punta con un test sintético y con una ejecución externa pequeña autorizada.
9. **Completar núcleo CRM del MVP.** Tabla paginada, búsqueda/filtros genéricos, ficha y edición segura de datos/notas/etapa; import idempotente y export privado; errores/cancelación/recovery de jobs. Preservar datos del scraper y los invariantes de dedup. No incluir Kanban ni el mailer productivo en MVP.
10. **Validar UX y paridad del scraper.** El usuario prueba localhost; GPT6-Luna recoge observaciones concretas, modifica interfaz y revalida ambos temas. Comparar fixtures/salidas del worker con los tests/código legado. No declarar paridad si no se portaron las reglas y pruebas relevantes.
11. **Demostrar calidad y operación local.** Correr unit/integration/e2e, lint, build, migraciones desde cero, reinicio de servicios, unavailable-worker path, recuperación de job y persistencia MariaDB. Entregar comandos de arranque/parada, ubicación de logs y forma de resetear solo datos sintéticos.
12. **Cerrar MVP.** Aceptación del usuario: app en localhost; tema claro/oscuro; textos sector-neutral; Kanban y secciones prohibidas ausentes; creación de perfil genérico; ejecución scraper a través del servicio local propio; estado/resultados persistidos y consultables; tests/build verdes; no hay producción/GitHub/Turso requerido. Después proponer fases de despliegue VPS, mailer y migración de datos.

No pasar de MVP local a despliegue/producción hasta revisar las precondiciones de seguridad, fuente de verdad, backup, credenciales, legales y autorización de correo en Fase 0/6/7. La meta final puede ser paridad completa; el MVP es una puerta de validación y no una declaración de que el mailer o toda función heredada ya se migraron.

---

## 5. Traducción de SQLite/Turso a MariaDB: decisiones técnicas obligatorias

1. **Inspeccionar antes de crear:** DDL efectivo de cada fuente, índices, constraints, número de filas, duplicados, máximos de IDs y formatos/timestamps. Identificar cuál es fuente de verdad lead, cola, ledger, supresión, plantillas y ajustes.
2. **InnoDB + `utf8mb4`:** definir explícitamente charset/collation. No depender de collation case-insensitive para implementar `dedup_key`; calcular claves en código con la misma normalización y guardar la clave canónica. Revisar longitudes e índices de texto.
3. **IDs:** mantener IDs históricos cuando sea posible y ajustar el siguiente autoincrement después de la carga. Definir todas las referencias antes de importar; evitar perder `lead_id` del ledger/cola/log.
4. **Timestamps:** mapear UTC/formatos de texto actuales (`store.ahora()` guarda UTC sin tzinfo) a una representación inequívoca en MariaDB. No mezclar hora de Madrid, UTC y timezone local del VPS. Las ventanas se calculan con `Europe/Madrid`, incluyendo DST.
5. **Upserts/importación:** `INSERT OR IGNORE`, índices parciales y algunas suposiciones SQLite no se trasladan literalmente. Diseñar operaciones MariaDB explícitas; no emplear una modalidad de `INSERT IGNORE` que silencie errores de datos inesperados.
6. **Dedup parcial de leads:** el índice SQLite excluye claves vacías; MariaDB no tiene el mismo índice parcial. Definir clave canónica nula para ausencia o una columna generada/estrategia equivalente, validar la versión instalada y probar muchas filas sin clave.
7. **Cola activa única:** SQLite usa índice único parcial sobre `email_queue(dominio)` cuando el estado es `pending` o `sending`. MariaDB no ofrece el mismo índice parcial. Implementar y probar una restricción equivalente (p. ej. columna generada nullable indexada única, compatible con la versión concreta) o una estrategia transaccional demostrablemente segura.
8. **Claim del mailer:** InnoDB sí ofrece transacciones, pero eso no autoriza a sustituir el claim por `SELECT` + `UPDATE` fuera de una transacción. La reclamación debe bloquear/actualizar una fila y confirmar el claim de forma segura ante procesos concurrentes; evaluar soporte de `SKIP LOCKED` solo después de conocer la versión de MariaDB. Usar lock/unique constraints donde corresponda, no declarar `SERIALIZABLE` indiscriminadamente.
9. **Ledger:** constraint único para la clave de contacto, inserción atómica y comprobación del resultado mediante filas afectadas/clave conflictiva; no usar `COUNT(*) antes/después` como mecanismo de concurrencia.
10. **Migraciones:** SQL numerado/versionado, migraciones forward-only probadas en una copia sintética y un proceso de rollback/restauración documentado. No ejecutar cambios de esquema improvisados desde el arranque de cada request como hace el `init_db()` actual.
11. **Tamaño y rendimiento:** medir volumen real y las consultas de Kanban/tabla/detalle/estadísticas antes de elegir índices. Usar paginación en API y límites; evitar cargar todos los leads en memoria para cada filtro. No optimizar a ciegas solo por «muchos datos».

---

## 6. API y módulos del backend

Diseño inicial que GPT6-Luna deberá concretar con los usos reales de las vistas. No es un contrato congelado.

- `auth`: login/logout/renovación de sesión, autorización, límites y protección CSRF según método de sesión elegido.
- `leads`: listado paginado y filtrado, contadores, detalle, actualización de campos comerciales, cambio de etapa, búsqueda, importación validada, exportación y borrado peligroso con confirmación/autorización.
- `scrap-profiles`: CRUD de perfiles, validación de ciudades/valores y selección del perfil para una ejecución.
- `pipeline-runs`: crear run, consultar progreso/historial/log sanitizado, cancelación, resultados y enlace/descarga privada de output cuando proceda.
- `guide-links`: CRUD y orden de `app_links`.
- `email`: estado, ajustes, plantillas, previsualización, encolado manual, cola, reintentos controlados, supresiones, historial, ledgers y tareas administrativas existentes.
- `health`: readiness/liveness sin filtrar configuración ni secretos.
- `internal/worker`: endpoints privados para claim/heartbeat/completar jobs e ingestión de resultados por lotes; autenticar servicio a servicio, validar `run_id` y hacer ingestión idempotente.

Usar DTOs/esquemas de validación explícitos, SQL parametrizado, ordenamiento permitido mediante allowlist, logs con redacción y respuestas de error coherentes. No permitir un endpoint general de SQL ni rutas de archivos sin validación.

---

## 7. Fases de migración y puertas de aceptación

Cada fase termina con criterios verificables. Si una puerta falla, no avanzar al siguiente corte.

### Fase 0 — Verificación de realidad y requisitos

**Objetivo:** confirmar estado productivo y fijar el inventario antes de codificar.

- Confirmar VPS, SO, recursos libres, versiones, dominio/TLS, método actual de despliegue, servicios/usuarios, puertos y políticas de firewall.
- Con el usuario, confirmar cuál BD tiene los datos vigentes (Turso y/o VPS/SQLite), forma de acceso/backups, volumen de leads y ficheros, y settings aprobados del mailer. No volcar datos personales a logs.
- Confirmar scheduler activo y desactivar la ambigüedad: systemd timer vs workflow GitHub. Verificar físicamente estado del workflow, timer y último envío; no inferirlo solo del repositorio.
- Obtener inventario de esquema/filas/constraints/índices, plantillas y configuración, sin secretos. Hacer una captura de backup cifrada comprobada y una restauración de prueba aislada.
- Recorrer cada vista y comando CLI; transformar los tests actuales en una matriz de comportamiento del CRM/mail/pipeline.
- Cerrar decisión de despliegue (systemd o Compose), autenticación inicial y política de retención/exportación.

**Aceptación:** inventario firmado por el usuario; fuente de verdad y único scheduler identificados; backup restaurado en entorno aislado; lista de funciones completa; ningún secreto ni lead expuesto.

### Fase 1 — Esqueleto del stack y despliegue de desarrollo

**Objetivo:** preparar una base ejecutable sin sustituir el CRM productivo.

- Crear estructura nueva separada (por ejemplo `apps/web`, `apps/api`, `workers/scraper`, `infra`, `migrations`) sin romper los comandos Python existentes. Añadir desde esta fase el wrapper de comandos locales definido arriba.
- Fijar versiones LTS/compatibles vigentes al iniciar la fase; lockfiles reproducibles. Angular y API TypeScript comparten tipos solo donde sea razonable, sin acoplar la BD al navegador.
- Arranque local de Angular, API, MariaDB de desarrollo y migraciones; config por entorno y secretos ignorados por Git.
- Añadir autenticación desde el comienzo y un usuario administrador inicial provisionado de forma segura. No publicar una UI sin auth porque la anterior usara Streamlit.
- Endpoints de health, logging estructurado con redacción y manejo uniforme de errores.

**Aceptación:** `./dev.sh setup` y `./dev.sh up` funcionan desde máquina limpia; UI/API/DB/worker local se identifican con `status`/`logs`; health checks correctos, migración vacía aplicable una sola vez, tests/lint/build verdes y ninguna conexión a Turso/SMTP de producción.

### Fase 2 — Esquema MariaDB y migración repetible

**Objetivo:** portar el modelo sin perder datos ni semánticas.

- Diseñar DDL MariaDB para tablas existentes y tablas de runs/worker si se aprueban.
- Implementar importación/exportación repetible desde copia de backup anonimizada o sintética. Añadir modo `dry-run` de importación que no escriba.
- Migrar todos los campos, IDs, estados, notas, perfiles, links, plantillas, settings, cola, ledger, logs y supresiones de la fuente confirmada.
- Probar Unicode, claves dedup, filas legacy, timestamps, entradas vacías y datos duplicados; elaborar reporte de conflictos sin borrado automático silencioso.
- Reconciliar recuentos por tabla, IDs, invariantes/keys únicos, sumas de controles y muestras sintéticas comparadas. Nunca mostrar muestras personales al agente/log.

**Aceptación:** varias ejecuciones de migración no duplican ni dañan; recuentos e invariantes coinciden; restauración MariaDB demostrada; ningún envío está habilitado.

### Fase 3 — API CRM y Angular sin pipeline/email productivos

**Objetivo:** replicar primero las funciones de trabajo manual.

- Implementar leads: listado paginado, filtros/estadísticas equivalentes, detalle, edición de notas y campos, transición de etapas, ordenamientos permitidos, import/export y borrado con doble confirmación.
- Implementar UI de Leads (Tabla/Detalle), búsqueda/perfiles y una página inicial útil; Guía solo si aporta onboarding genérico. No implementar Kanban. Retirar las tres secciones de Guía indicadas arriba. Mantener etiquetas en español y estados claros de carga/error/vacío.
- Reimplementar filtros compartidos y acciones de fila. Preservar la lógica de dedup y no sobrescribir notas/etapas por una importación ordinaria.
- API de perfil con todas las opciones que realmente existen y validación de parámetros.
- Añadir pruebas API/componentes y pruebas de autorización; probar el dataset solo en entorno de ensayo con copia protegida.

**Aceptación:** el usuario puede completar las operaciones manuales retenidas del CRM; pruebas cubren permisos, paginación, filtros, persistencia, duplicados, edición concurrente y errores; se valida tema claro/oscuro; no hay escritura sobre producción vieja ni rutas/componentes Kanban.

### Fase 4 — Scraper Python coexistente y pipeline autohospedado

**Objetivo:** ejecutar las mismas búsquedas desde el nuevo panel sin reescribir Playwright.

- Mantener `maps_scraper.py`, `enricher.py`, configuración y lógica probada inicialmente. Empaquetar dependencias Chromium/Playwright de forma reproducible para el VPS; ejecutar con usuario no root, recursos y tiempo límite controlados.
- Sustituir `pipeline_runner.py` + GitHub como vía operativa por jobs durables coordinados desde Node y worker Python privado.
- Guardar perfil y parámetros como snapshot inmutable asociado al `run_id`; soportar modos scraper/enricher/pipeline, progreso, errores, cancelación y recuperación tras reinicio.
- Importar JSON/resultados por lotes idempotentes; guardar outputs/versionado con permisos privados y retención definida. Proteger log y outputs con privacy filtering; sin artifacts públicos.
- Respetar límites aplicables del sitio, minimizar solicitudes y no implementar evasión de controles de acceso o de seguridad de la plataforma.

**Aceptación:** `./dev.sh scrape` usa el worker local y nunca cae a servicios remotos; ejecución sintética/staging de cada modo, resultados con conteos coherentes, dedup idéntica a tests, progreso observable, reinicio/recovery probado y worker inaccesible públicamente. Nunca ejecutar un scraping masivo real sin aprobación explícita.

### Fase 5 — Email parity y scheduler único

**Objetivo:** preservar íntegramente los controles del mailer antes de mover el envío.

- Reimplementar UI Emails y lógica, o mantener temporalmente el worker Python como puente, pero no activar ambos.
- Portar ventana `Europe/Madrid`/DST, días laborables, ritmo/jitter configurable, rampa, tope manual/máximo, freno por tasa de fallos, claim/recovery de `sending`, supresiones, ledger, templates, preview, MIME texto+HTML, SMTP, logs, heartbeat/avisos y actualización de etapa.
- Revisar cuidadosamente `sender.py`: SMTP STARTTLS, cabeceras, `List-Unsubscribe`, `Reply-To`, modos de redirección/dry-run y qué estados/ledger dejan. Conservar el comportamiento aprobado; una modificación requiere decisión y tests explícitos.
- Crear tests de concurrencia real contra MariaDB/InnoDB con dos workers simultáneos: un único contacto por clave, una sola reserva, claims distintos/seguros y ninguna cola duplicada en estados activos.
- Secretos SMTP del servicio en almacén local restringido; rotar la contraseña que los documentos identifican como posiblemente expuesta. Nunca incluirla en commits, env-example con valor real, logs o reporte del agente.
- Ejecutar primero `dry-run` con datos falsos y verificar que no modifica una reserva real; cambiar expresamente su semántica si hace falta. Luego pruebas de SMTP solo a buzón propio y con la autorización del usuario.

**Aceptación:** batería port de `tests/test_fase6.py` y escenarios concurrentes verdes; ventana/DST y warm-up validados; supresión/ledger no saltables; backup/restauración conserva controles; solo un scheduler/emisor; OK del usuario antes de cualquier activación real.

### Fase 6 — Hardening y operaciones del VPS

**Objetivo:** producir un despliegue que sobreviva reinicios y pueda recuperarse.

- Nginx con TLS, cabeceras seguras y proxy; Angular compilado estático; API y workers como unidades separadas con reinicio/health checks y límites de recursos.
- Firewall: solo exponer HTTPS/SSH controlado; MariaDB escucha en localhost/red privada, no en Internet. Usuarios/privilegios separados y mínimos.
- Auth con credenciales robustas, cookies seguras y protección CSRF según diseño; rate limits, validación de archivos y protección de endpoints de administración. Si no hay necesidad de multiusuario, mantener modelo simple pero no público/abierto.
- Backups automáticos cifrados de MariaDB y ficheros necesarios, copias fuera del VPS, retención y alarmas. Probar restauración completa con frecuencia. Documentar RPO/RTO y plan si el VPS desaparece.
- Logs, métricas básicas, alertas de espacio/servicios/backup y rotación. Logs nunca contendrán contenido de email, credenciales ni datos de leads en texto claro innecesarios.
- Documentar actualización y rollback de API, UI, migraciones, worker, Chromium y MariaDB.

**Aceptación:** despliegue ensayado desde cero, reinicio VPS simulado, backup restaurado, TLS/verificación de puertos y checklist operativo aprobados.

### Fase 7 — Cutover y retiro gradual de Streamlit/Turso/GitHub Actions

**Objetivo:** cambiar al sistema nuevo sin pérdida ni doble envío.

1. Acordar ventana de mantenimiento; bloquear temporalmente importaciones y envíos en el sistema antiguo.
2. Tomar backup final cifrado de BD y outputs; verificar que puede restaurarse; anotar el watermark/fecha y versiones.
3. Importar delta final a MariaDB y comparar los checks de Fase 2.
4. Dejar antiguo CRM/DB en modo read-only o parado; apuntar Angular/API/worker solo a MariaDB.
5. Iniciar **un solo** mailer; confirmar config/ledger/supresiones primero. No conservar timer viejo ni schedule GitHub activos contra otra BD o la nueva.
6. Smoke tests sin envío y validación por el usuario; monitorizar logs y backups. Habilitar correo únicamente con aprobación explícita y controles de prueba.
7. Mantener el sistema viejo y su backup recuperables durante periodo acordado. Retirar secretos/Turso/Streamlit/GitHub PAT solo después de validar la nueva operación y los backups.

**Aceptación:** recuentos e invariantes finales reconciliados; panel funcional; scraper y mailer bajo control; un único origen de escritura y scheduler; rollback ensayado; consentimiento del usuario para decommission.

---

## 8. Plan de pruebas de paridad mínimo

| Área | Comportamientos que no deben perderse |
|---|---|
| Leads | Dedup por nombre+dirección/nombre+ciudad, limpieza Unicode, campos enriquecidos, notas/etapa persistentes y colapso de duplicados conservando la fila más rica. |
| Etapas | Vocabulario válido y normalización de estados legacy/desconocidos a `Nuevo`; separación de etapa comercial y progreso de scraping. |
| Perfiles | Ciudades, query templated, min reseñas/puntuación, filtro web, scrolls, `auto_import`; el run conserva snapshot aunque el perfil cambie después. |
| Runs | Scraper/enricher/pipeline, estado, fecha, logs sanitizados, archivos, importación idempotente, fallo/cancelación/recovery. |
| Mail | Contact key exacta, un envío máximo por clave, ledger-before-send, suppressions, claim bajo carrera, reaper de claims antiguos, intents, reportes y settings. |
| Calendario | Lunes-viernes, `Europe/Madrid`, cambio DST, horario configurable, siguiente envío UTC, límites diarios por día local, warm-up y freno por fallos. |
| UI | Filtros, contadores, tabla, ficha, import/export, perfiles, emails cuando se active esa fase, estados vacíos, confirmaciones, errores, permisos y modo claro/oscuro/sistema. Kanban y las secciones de Guía retiradas no se implementan. |
| Privacidad | No secretos en repositorio, no emails/nombres en logs/artifacts públicos, descarga de CSV autenticada, backups cifrados, acceso DB no público. |
| Operación | Arranque/parada, restart tras crash, no jobs duplicados, backup/restore, migración y rollback. |

Usar tests sintéticos. Los tests existentes (`tests/test_bug2.py`–`test_bug5.py`, `test_fase4_riesgos.py`, `test_fase5.py`, `test_fase6.py`) son referencia inicial; revisar código para inventariar todas las comprobaciones y mover/recrear las que dependan de Streamlit/Turso. El antiguo test de paridad Turso/SQLite deja de ser un objetivo final, pero su comportamiento de datos y errores asociados se conserva.

---

## 9. Seguridad, privacidad, rendimiento y límites de alcance

- Este CRM contiene contactos comerciales y notas; tratarlo como información privada aunque no sea historial clínico. No incluir datos de pacientes ni reutilizar el diseño de PsycoERP clínico como si fueran los mismos datos.
- Revisar base legal, oposiciones/bajas, obligaciones de identificación y reglas del proveedor/plataforma antes de continuar prospección automatizada. Tener teléfono/web/email no equivale a consentimiento. La migración no constituye asesoramiento legal ni permiso de contacto.
- VPS propio significa más control, pero también responsabilidad por parches, firewall, TLS, backups, recuperación y monitorización. MariaDB en el mismo VPS reduce latencia, pero no evita pérdida si falla el disco/servidor: mantener copia fuera del VPS.
- La mejora de velocidad debe medirse con una baseline: tiempo de carga de vistas y consultas, p95 de API, tamaño de BD, tiempo de scraper y uso de CPU/RAM. Angular/API evitarán el rerun completo de Streamlit y MariaDB en el mismo VPS reduce round-trips a Turso, pero el navegador/sitio externo probablemente seguirá dominando el tiempo de scraping.
- Limitar peticiones y paralelismo de Playwright en función de recursos y políticas del sitio. No declarar que cambiar a Node o Java acelera el scraping sin benchmark comparable.
- Migración inicial no requiere reescribir el scraper, añadir Redis/Kubernetes, microservicios múltiples, Astro ni una app móvil. Evitar complejidad prematura; si luego se necesita una cola externa, evaluar desde métricas.

---

## 10. Fuentes que GPT6-Luna debe revisar

Leer como mínimo antes de implementar:

- `README.md` (documento maestro; stack/arquitectura, decisiones, fases, mailer y operación).
- `context/ANALISIS_LEADS_TURSO.md` (consultas y semánticas de contactos/cola/supresiones).
- `context/VPS_MAILER.md` (estado y precauciones del mailer VPS; confirmar contra producción).
- `context/session-handoff.md` (decisiones aprobadas y riesgos de credenciales; puede contener información histórica obsoleta).
- `context/github-actions-plan.md`, `context/next-steps.md`, `context/How_To.md` (separar backlog de estado vigente).
- `src/crm/db.py`, `src/crm/turso_http.py`, `src/crm/pipeline_runner.py`, `src/crm/app.py`, todos los módulos de `src/crm/views/`.
- `src/models/lead.py`, `src/scraper/`, `run_scraper.py`, `run_enricher.py`, `run_pipeline.py`.
- Todos los módulos de `src/mailer/`, `run_mailer.py`, `run_backup.py`.
- `requirements.txt`, `tests/`, `.github/workflows/*.yml`, `.env.example`, `.gitignore`.

### Paquete de código legado necesario para un proyecto nuevo

Como GPT6-Luna no tendrá acceso a este repositorio, el usuario debe adjuntar/subir al proyecto nuevo, idealmente como ZIP limpio o archivos fuente, al menos:

- Scraper: `src/scraper/maps_scraper.py`, `src/scraper/config.py`, `src/scraper/privacy.py`, `run_scraper.py`.
- Enricher: `src/scraper/enricher.py`, `run_enricher.py`, y los modelos/helpers que importe.
- Contrato de datos/dedup: `src/models/lead.py`, `src/crm/db.py` (solo código, no base), `src/crm/pipeline_runner.py` y `run_pipeline.py`.
- UI para inventariar comportamiento visual: `src/crm/app.py` y todos los ficheros `src/crm/views/*.py`, especialmente `guia.py`, `scrap.py`, `tabla.py`, `detalle.py`, `emails.py` y `_components.py`. Kanban solo se adjunta para confirmar las funciones que explícitamente se van a excluir.
- Mailer y pruebas para la fase posterior: `src/mailer/*.py`, `run_mailer.py`, `run_backup.py`, `tests/*.py`.
- Documentación de decisiones: `README.md`, los MD de `context/` enumerados arriba y `requirements.txt`.

No adjuntar `data/`, `crm.db`/WAL/SHM, CSV/JSON con leads, `.env`, secrets, tokens, contraseñas SMTP, artifacts ni logs que puedan contener datos personales. Si se necesitan fixtures, anonimizar/sintetizar previamente. Si el usuario no quiere adjuntar todo de una vez, primero enviar scraper/enricher/modelo/tests relevantes y desarrollar UI con datos ficticios; no prometer paridad completa hasta revisar cada dependencia.

### Datos que siguen pendientes de confirmar con el usuario

1. VPS/OS/CPU/RAM/disco y versiones efectivamente instaladas; no están fijados aquí.
2. Fuente de verdad actual y estado real de Turso/SQLite, timer systemd y workflows GitHub.
3. Cantidad/crecimiento de leads y tamaño/retención de outputs.
4. Settings activos del mailer en la BD productiva y autorización para seguir enviando.
5. Si se requiere multiusuario/roles o bastará un administrador.
6. Política de backup, retención y objetivo tolerable de pérdida/interrupción (RPO/RTO).

**No bloquean preparar código local inicial**, pero sí bloquean cualquier corte, importación real, exposición pública o habilitación del mailer.

