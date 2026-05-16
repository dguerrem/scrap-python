# Pipeline Automation via GitHub Actions

## Arquitectura

```
CRM (Streamlit Cloud)         Turso (BD)
  │                              ↑
  ├── Kanban, tabla, etc. ──────┘
  │
  └── Botón "🚀 Lanzar Pipeline"
        │
        ▼
  GitHub Actions (workflow_dispatch + cron)
        │
        ├── Instala Python + Playwright
        ├── Ejecuta scraper (ciudades seleccionadas)
        ├── Ejecuta enricher
        └── Escribe leads directamente en Turso ✅
```

## Workflow a crear: `.github/workflows/pipeline.yml`

### Triggers

- **Manual** (`workflow_dispatch`): disparado desde el CRM via GitHub API
- **Programado** (`schedule`): cron configurable (ej. cada noche a las 4AM)

```yaml
on:
  schedule:
    - cron: "0 4 * * *" # Cada día a las 4:00 AM UTC
  workflow_dispatch:
    inputs:
      cities:
        description: "Ciudades separadas por coma"
        required: true
        default: "Madrid,Barcelona,Bilbao,Málaga"
```

### Secrets necesarios en GitHub

- `TURSO_DATABASE_URL` — URL de la BD Turso
- `TURSO_AUTH_TOKEN` — Token de autenticación Turso

### Steps del workflow

1. Checkout repo
2. Setup Python 3.11
3. `pip install -r requirements.txt`
4. `playwright install chromium --with-deps`
5. `python run_pipeline.py --cities ${{ inputs.cities }} --headless`
6. Los scripts ya escriben en Turso si las env vars están configuradas

## Cambios necesarios en el CRM (`src/crm/app.py`)

### Nuevo tab "🚀 Pipeline"

- Selector de ciudades (multiselect con las de `config.py`)
- Botón "Lanzar Pipeline" → llama a GitHub API `POST /repos/{owner}/{repo}/actions/workflows/{id}/dispatches`
- Botón "Lanzar solo Scraper" / "Lanzar solo Enricher"
- Indicador de estado: consulta GitHub API para ver si hay un run activo
- Historial de ejecuciones recientes (últimos 10 runs con status y duración)

### Secret necesario en Streamlit

- `GITHUB_PAT` — Personal Access Token con permisos `repo` y `actions`

## Cambios necesarios en los scripts

### `run_pipeline.py` / `run_scraper.py` / `run_enricher.py`

- Cuando detecten `TURSO_DATABASE_URL` en env, tras generar el JSON,
  importar leads directamente a Turso (llamar `import_leads()`)
- Así el CRM refleja los resultados sin intervención manual

## Cron — Opciones de programación

| Frecuencia     | Cron              | Notas                   |
| -------------- | ----------------- | ----------------------- |
| Cada noche 4AM | `0 4 * * *`       | UTC → 6AM España verano |
| Lunes y jueves | `0 4 * * 1,4`     | 2 veces/semana          |
| Cada 3 días    | `0 4 */3 * *`     | ~10 veces/mes           |
| Solo manual    | (quitar schedule) | Solo workflow_dispatch  |

## Límites GitHub Actions (gratis)

- **Repo público**: minutos ilimitados
- **Repo privado**: 2.000 min/mes gratis
- Pipeline actual tarda ~120 min → ~16 ejecuciones/mes en privado
- Timeout máximo por job: 6 horas

## Features pendientes del CRM

### Acciones de Pipeline (tab "🚀 Pipeline")

1. **Lanzar solo Scraper** — Selector de ciudades + botón → dispara GitHub Action solo con scraper
2. **Lanzar solo Enricher** — Botón → dispara GitHub Action solo con enricher sobre leads ya scrapeados
3. **Lanzar Pipeline completa** — Selector de ciudades + botón → dispara scraper + enricher juntos
4. **Estado en vivo** — Indicador de si hay un pipeline corriendo, con link al log de GitHub
5. **Historial de ejecuciones** — Últimos 10 runs con status, ciudades, duración y leads generados

### Acciones de Gestión de Datos (sidebar o tab)

6. **🗑️ Vaciar todos los leads** — Botón con confirmación (doble click o checkbox) → `DELETE FROM leads`
7. **🗑️ Resetear leads por ciudad** — Selector de ciudad + botón → borrar solo los de esa ciudad
8. **📤 Exportar leads** — Descargar JSON/CSV de los leads actuales (filtrados o todos)

### Programación automática

9. **Cron configurable** — Selector en el CRM para elegir frecuencia (diario, L-J, semanal, desactivado)
10. **Notificación** — Indicar en el CRM cuándo fue la última ejecución automática y cuántos leads nuevos trajo
