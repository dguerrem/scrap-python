# Next Steps — Features del CRM

> Todas las features deben funcionar en local (SQLite) y en cloud (Turso).

---

## Feature 1: Vaciar leads ✅ FÁCIL

**Descripción**: Botón que resetea la BD — borra todos los leads y deja el CRM como nuevo.

**Implementación**:
- Botón "🗑️ Vaciar todos los leads" en sidebar o tab de gestión
- Doble confirmación (checkbox "Estoy seguro" + botón) para evitar borrados accidentales
- Ejecuta `DELETE FROM leads`
- Funciona igual en SQLite y Turso

**Complejidad**: Baja (~20 líneas)

---

## Feature 2: Personalizador de Scrap ✅ FACTIBLE

**Descripción**: Formulario en el CRM para configurar los parámetros del scraper antes de lanzarlo. Permite crear "perfiles de búsqueda" distintos según el objetivo comercial.

**Parámetros configurables**:
- Ciudades (multiselect)
- Query de búsqueda (texto libre, ej. "Clínica de psicología en {city}", "Psicólogo en {city}")
- Min reseñas (slider, 0-100)
- Min puntuación (slider, 0.0-5.0)
- Requiere sitio web: Sí / No / Solo sin web
- Max scrolls (slider, 5-50)
- Delays (anti-bloqueo)

**Casos de uso**:
- Scrap estándar: clínicas con web, >4★, >20 reseñas → para vender PsycoERP
- Scrap sin web: clínicas SIN sitio web → para vender landing pages
- Scrap amplio: bajar filtros para captar más leads de menor calidad

**Implementación**:
- Nuevo tab o modal con formulario de parámetros
- Guardar perfiles en BD (nueva tabla `scrap_profiles`)
- Al lanzar pipeline (cuando implementemos GitHub Actions), usa el perfil seleccionado
- En local: genera un JSON de config que los scripts consumen

**Complejidad**: Media (~150-200 líneas)

---

## Feature 3: Kanban Drag & Drop ⚠️ COMPLEJO

**Descripción**: Poder arrastrar leads entre columnas del Kanban sin abrir el expander ni usar selectbox.

**Problema**: Streamlit no soporta drag & drop nativo. Las columnas son estáticas.

**Opciones**:

### Opción A: `streamlit-elements` (recomendada)
- Componente de terceros que permite usar Material UI dentro de Streamlit
- Soporta dashboards con drag & drop real
- Pros: funciona bien, look profesional
- Contras: dependencia externa, API diferente al resto del CRM

### Opción B: HTML/JS custom con `st.components.v1.html`
- Inyectar un Kanban en JavaScript puro (ej. con SortableJS)
- Comunicación bidireccional con Streamlit via `Streamlit.setComponentValue()`
- Pros: control total, sin dependencias
- Contras: mucho más código, más difícil de mantener

### Opción C: Mejorar UX sin drag & drop
- En lugar de drag & drop, poner botones rápidos de acción en cada card:
  `→ Contactado` `→ Demo` `→ Descartado`
- Un solo click para mover de etapa (sin abrir expander)
- Pros: fácil de implementar, funciona en móvil
- Contras: no es "real" drag & drop

**Recomendación**: Empezar con Opción C (botones rápidos) que es inmediata, y evaluar Opción A más adelante si se necesita UX más visual.

**Complejidad**: C = Baja | A = Alta | B = Muy alta

---

## Feature 4: Historial de Pipelines ✅ FACTIBLE

**Descripción**: Registro de cada ejecución de pipeline con sus resultados y los JSONs generados.

**Implementación**:
- Nueva tabla `pipeline_runs`:
  ```sql
  id INTEGER PRIMARY KEY,
  tipo TEXT,              -- 'scraper', 'enricher', 'pipeline'
  ciudades TEXT,          -- 'Madrid,Barcelona'
  parametros TEXT,        -- JSON con el perfil de scrap usado
  leads_raw TEXT,         -- JSON completo de leads_raw
  leads_enriched TEXT,    -- JSON completo de leads_enriched
  total_scrapeados INT,
  total_enriquecidos INT,
  estado TEXT,            -- 'running', 'completed', 'failed'
  started_at TIMESTAMP,
  finished_at TIMESTAMP
  ```
- Tab "📜 Historial" en el CRM:
  - Lista de ejecuciones con fecha, tipo, ciudades, estado, contadores
  - Click en una ejecución → ver detalle + descargar JSONs
  - Botón "Importar leads de esta ejecución" → carga esos leads al CRM

**Complejidad**: Media (~200-250 líneas entre DB + UI)

---

## Orden de implementación sugerido

| Prioridad | Feature | Esfuerzo |
|-----------|---------|----------|
| 1 | Vaciar leads | 15 min |
| 2 | Personalizador de scrap | 1-2h |
| 3 | Historial de pipelines | 1-2h |
| 4 | Kanban mejorado (botones rápidos) | 30 min |
| 5 | Kanban drag & drop real | 3-4h |

---

## Features futuras (por documentar)

- GitHub Actions: lanzar pipes desde el CRM (ver `github-actions-plan.md`)
- Programación cron desde el CRM
- Exportar leads (JSON/CSV)
- Resetear leads por ciudad
- Envío de emails desde el CRM
- Dashboard de métricas de conversión
