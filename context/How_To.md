# How To — Comandos locales

> Siempre desde `/Users/dguerrero/Desktop/Everything/Projects/Psyco/scrap-python`
> El venv se activa automáticamente con cada bloque.

## Activar entorno

```bash
source venv/bin/activate
```

---

## Scraper (Google Maps)

```bash
# Todas las ciudades del config
python run_scraper.py --headless

# Ciudades concretas
python run_scraper.py --cities Madrid,Barcelona --headless
```

---

## Enricher (emails + director desde webs)

```bash
# Enriquecer todos los leads scrapeados
python run_enricher.py --headless

# Limitar a N leads (para pruebas)
python run_enricher.py --headless --limit 20
```

---

## Pipeline completa (scraper + enricher)

```bash
# Todas las ciudades
python run_pipeline.py --headless

# Ciudades concretas
python run_pipeline.py --cities Madrid,Bilbao --headless

# Solo enricher (saltar scraping)
python run_pipeline.py --skip-scraping --headless

# Solo scraper (saltar enrichment)
python run_pipeline.py --skip-enrichment --headless
```

---

## CRM local

```bash
streamlit run src/crm/app.py
# Abre http://localhost:8501
```

---

## Datos

| Fichero                    | Contenido                         |
| -------------------------- | --------------------------------- |
| `data/leads_raw.json`      | Leads scrapeados (sin enriquecer) |
| `data/leads_enriched.json` | Leads con emails y director       |
| `data/crm.db`              | BD local del CRM                  |

### Resetear BD local

```bash
rm data/crm.db
```

---

## Git

```bash
git add -A && git commit -m "mensaje" && git push
```
