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
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Ruta a un fichero JSON con el perfil de scrap (parámetros personalizados).",
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

    # Cargar perfil si se especificó
    profile = None
    if args.profile:
        from pathlib import Path
        profile = __import__("json").loads(Path(args.profile).read_text(encoding="utf-8"))

    run(cities=cities, headless=args.headless, profile=profile)


if __name__ == "__main__":
    main()
