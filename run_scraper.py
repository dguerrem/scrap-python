"""
PsycoLead-Scraper — Entry point

Uso desde la terminal (siempre con el virtualenv activado):

  python run_scraper.py                            # Todas las ciudades, navegador visible
  python run_scraper.py --cities Madrid,Barcelona  # Solo esas ciudades
  python run_scraper.py --headless                 # Sin mostrar el navegador
"""

import argparse
import logging

from src.scraper.maps_scraper import run


def main():
    parser = argparse.ArgumentParser(
        description="PsycoLead-Scraper: Extracción de leads de Google Maps"
    )
    parser.add_argument(
        "--cities",
        type=str,
        default=None,
        help='Ciudades separadas por coma. Ej: --cities "Madrid,Barcelona"',
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Ejecutar sin mostrar el navegador (modo invisible).",
    )
    args = parser.parse_args()

    # Configurar logging (los mensajes del scraper se muestran en consola)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Parsear ciudades si se pasaron por argumento
    cities = None
    if args.cities:
        cities = [c.strip() for c in args.cities.split(",")]

    run(cities=cities, headless=args.headless)


if __name__ == "__main__":
    main()
