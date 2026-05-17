"""
Entry point para la Fase 2 — Enriquecimiento de leads.
Visita cada web de clínica y extrae director + emails.

Uso:
    python run_enricher.py                     # Todos los leads, navegador visible
    python run_enricher.py --limit 5           # Solo los 5 primeros (para test)
    python run_enricher.py --headless          # Sin abrir navegador
    python run_enricher.py --limit 5 --headless
"""

import argparse
import logging

from src.scraper.enricher import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fase 2: Enriquecer leads con web scraping")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Número máximo de leads a enriquecer (por defecto: todos)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Ejecutar navegador en modo headless (sin ventana visible)",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        dest="run_id",
        help="Identificador de la ejecución para guardar copia timestamped",
    )
    args = parser.parse_args()

    run(limit=args.limit, headless=args.headless, run_id=args.run_id)
