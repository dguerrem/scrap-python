# PsycoLead-Scraper

Pipeline de extracción y enriquecimiento de leads B2B para la prospección de clínicas de psicología medianas en España. Primera fase de la estrategia de ventas de **PsycoERP**.

---

## Contexto del Producto: PsycoERP

Software de gestión (ERP) nicho diseñado exclusivamente para psicólogos y clínicas de salud mental, desarrollado bajo modelo **High-Ticket de pago único** (2.500 € por licencia).

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
- **Servicio incluido:** soporte 24/7 y mantenimiento durante el primer año + migración de datos históricos y formación del equipo ("Guante Blanco") a coste cero.
- **Infraestructura:** el ERP se instala en un VPS a nombre del cliente (~10 €/mes) usando sus propias cuentas de API. Pagan exactamente lo que consumen.

---

## Cliente Ideal (ICP)

- **Target:** clínicas de psicología medianas (gabinetes de 3 a 15 profesionales).
- **Motivación:** flujos complejos de reparto de salas y comisiones; hartos de suscripciones eternas a plataformas genéricas donde sus datos están en servidores de terceros.
- **Gatekeeper:** recepcionistas que filtran llamadas → la prospección evita el teléfono a puerta fría y la bandeja `info@`.

---

## Estrategia de Prospección (Go-To-Market)

Objetivo: **3-5 clientes mensuales** mediante prospección outbound quirúrgica.

1. **Extracción Local** — Scraping de clínicas medianas en Google Maps.
2. **Enriquecimiento** — Nombre del Director/Propietario + email directo.
3. **Contacto Asíncrono** — Video-Pitch de 2 min (Loom) dirigido al director mostrando dashboard, calendario y ahorro financiero.
4. **Cierre** — Llamada de descubrimiento (15 min) → Demo → Cierre a 2.500 €.

---

## Stack Tecnológico

| Componente    | Tecnología            |
| ------------- | --------------------- |
| Lenguaje      | Python 3.9+           |
| Scraping core | Playwright (headless) |
| CRM ligero    | Streamlit + SQLite    |
| Salida datos  | JSON / CSV            |

---

## Estructura del Proyecto

```
scrap-python/
├── context/                  # Briefing del proyecto
├── src/
│   ├── scraper/
│   │   ├── maps_scraper.py   # Fase 1: Scraping Google Maps
│   │   ├── enricher.py       # Fase 2: Enriquecimiento webs
│   │   └── config.py         # Configuración (ciudades, filtros, delays)
│   ├── crm/
│   │   └── app.py            # Fase 3: CRM Kanban (Streamlit)
│   └── models/
│       └── lead.py           # Modelo de datos del lead
├── data/                     # Output: JSONs y CSVs generados
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Plan de Desarrollo

### Fase 0 — Setup del Entorno ✅

- Crear **virtualenv** (`venv/`) dentro del proyecto.
- Definir estructura de carpetas.
- Crear `requirements.txt` con dependencias.
- Instalar Playwright + navegadores Chromium.
- Crear `.gitignore` (venv, data, **pycache**, .env).

---

### Fase 1 — Minería en Google Maps

Iterar búsquedas tipo `"Clínica de psicología"` sobre un listado de ciudades de España.

**Filtros de cualificación (críticos):**

- Número de reseñas **> 20**.
- Puntuación **≥ 4.0**.
- Debe tener página web (sin URL → descartar).

**Datos guardados por clínica (columnas del CSV/JSON):**

| Columna      | Descripción                                     |
| ------------ | ----------------------------------------------- |
| `nombre`     | Nombre del negocio                              |
| `ciudad`     | Ciudad de la búsqueda (Madrid, Barcelona, etc.) |
| `direccion`  | Dirección completa                              |
| `telefono`   | Teléfono de contacto                            |
| `url`        | Página web de la clínica                        |
| `puntuacion` | Rating en Google Maps (≥ 4.0)                   |
| `resenas`    | Número de reseñas (> 20)                        |

**Tareas técnicas:**

1. Configuración de ciudades/CP objetivo.
2. Navegación Playwright (headless) + scroll infinito del panel de resultados.
3. Extracción de datos por resultado.
4. Anti-bloqueo: delays aleatorios, user-agent rotativo, timeouts.
5. Deduplicación por nombre + dirección.
6. Output a `data/leads_raw.json` y `data/leads_raw.csv`.

**Test:** Ejecutar contra 2-3 ciudades → validar ≥ 15 leads limpios con columna `ciudad` correcta.

---

### Fase 2 — Enriquecimiento de Leads

Por cada URL de la Fase 1, el script visita la web de la clínica y:

1. **Extracción del Director (Aviso Legal):** escanea el HTML buscando enlaces a "Aviso Legal", "Política de Privacidad" o "Condiciones". Dentro de esas páginas busca palabras clave como `Responsable`, `Titular del sitio web`, `DNI`, `NIF` y aísla el nombre completo de la persona física o sociedad administradora.

2. **Extracción de Email (Regex):** busca patrones de correo en el HTML completo y los clasifica:
   - **Genéricos:** `info@`, `contacto@`, `hola@`, etc.
   - **Directos:** `nombre@`, `direccion@`, `gerencia@`, etc.

3. Manejo de errores: webs caídas, timeouts, redirects, páginas sin aviso legal.
4. Output a `data/leads_enriched.json` y `data/leads_enriched.csv`.

**Test:** Tomar 5 leads de Fase 1, enriquecer y validar manualmente contra las webs reales.

---

### Fase 3 — CRM Kanban Ligero (Streamlit)

UI mínima en Streamlit + SQLite para gestionar el pipeline de ventas.

| Estado       | Descripción                            |
| ------------ | -------------------------------------- |
| `Scraped`    | Datos crudos de Google Maps            |
| `Enriched`   | Con nombre del director y email válido |
| `Video Sent` | Pitch enviado                          |
| `Meeting`    | Reunión agendada                       |
| `Closed`     | Cliente ganado                         |

**Funcionalidades:**

- Carga de leads enriquecidos.
- Vista Kanban con columnas por estado.
- Mover leads entre estados.
- Filtros por ciudad, puntuación, tiene email directo.
- Persistencia en SQLite (`data/crm.db`).
- Métricas básicas: leads por estado, tasa de conversión.

**Test:** Cargar 10 leads, mover entre estados, refrescar y verificar persistencia.

---

### Fase 4 — Integraciones y Automatización ⏸️ SOLO DOCUMENTADA — NO SE IMPLEMENTA

> Esta fase queda registrada como roadmap futuro. No se desarrollará en esta iteración.

- Integración con API de **Hunter.io** (fallback de emails cuando la extracción web falla).
- Automatización del envío de video-pitch.
- Export a Notion / Airtable.
- Scheduling con cron para scraping periódico.

---

## Orden de Trabajo

```
Fase 0 (Setup) → Fase 1 (Maps) → Test → Fase 2 (Enrich) → Test → Fase 3 (CRM) → Test
```

> Cada fase se desarrolla, se testea, y se avanza a la siguiente. Nada de avanzar sin validar.
