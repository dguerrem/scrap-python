"""
Pipeline completo: Scraping de Google Maps → Enriquecimiento web.
Ejecuta ambas fases en secuencia, sin intervención manual.

Uso:
    python run_pipeline.py                      # 10 ciudades, headless
    python run_pipeline.py --cities Madrid,Barcelona
    python run_pipeline.py --skip-scraping      # Solo enricher (si ya tienes leads_raw)
    python run_pipeline.py --skip-enrichment    # Solo scraping
"""

import argparse
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline: Scraping + Enrichment")
    parser.add_argument(
        "--cities",
        type=str,
        default=None,
        help="Ciudades separadas por coma (por defecto: todas)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Navegador headless (por defecto: sí)",
    )
    parser.add_argument(
        "--skip-scraping",
        action="store_true",
        help="Saltar fase de scraping (solo enricher)",
    )
    parser.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Saltar fase de enrichment (solo scraping)",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Ruta a fichero JSON con perfil de scrap personalizado.",
    )
    args = parser.parse_args()

    cities = [c.strip() for c in args.cities.split(",")] if args.cities else None

    # Cargar perfil si se especificó
    profile = None
    if args.profile:
        from pathlib import Path as _P
        profile = __import__("json").loads(_P(args.profile).read_text(encoding="utf-8"))

    start = time.time()

    # ─── FASE 1: Scraping de Google Maps ───
    if not args.skip_scraping:
        log.info("=" * 60)
        log.info("FASE 1 — SCRAPING DE GOOGLE MAPS")
        log.info("=" * 60)
        from src.scraper.maps_scraper import run as run_scraper
        run_scraper(cities=cities, headless=args.headless, profile=profile)
    else:
        log.info("Scraping saltado (--skip-scraping)")

    # ─── FASE 2: Enriquecimiento web ───
    if not args.skip_enrichment:
        log.info("")
        log.info("=" * 60)
        log.info("FASE 2 — ENRIQUECIMIENTO WEB")
        log.info("=" * 60)
        from src.scraper.enricher import run as run_enricher
        run_enricher(headless=args.headless)
    else:
        log.info("Enrichment saltado (--skip-enrichment)")

    elapsed = time.time() - start
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    log.info("")
    log.info(f"Pipeline completado en {mins}m {secs}s")
