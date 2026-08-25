"""
Configuración del scraper — PsycoLead-Scraper
Edita este archivo para ajustar ciudades, filtros y delays.
"""

# ======================================================
# CIUDADES OBJETIVO
# ======================================================
CITIES = [
    "Madrid",
    "Barcelona",
    "Valencia",
    "Sevilla",
    "Málaga",
    "Bilbao",
    "Zaragoza",
    "Murcia",
    "Palma de Mallorca",
    "Las Palmas de Gran Canaria",
    "Pontevedra",
]

# Plantilla de búsqueda (no tocar {city}, se reemplaza automáticamente)
SEARCH_QUERY = "Clínica de psicología en {city}"

# ======================================================
# FILTROS DE CUALIFICACIÓN
# ======================================================
MIN_REVIEWS = 20    # Mínimo de reseñas para considerar el lead
MIN_RATING = 4.0    # Mínimo de puntuación (estrellas)

# ======================================================
# ANTI-BLOQUEO (delays en segundos, rango [min, max])
# ======================================================
DELAY_BETWEEN_SEARCHES = (5, 10)    # Pausa entre ciudades
DELAY_BETWEEN_RESULTS = (2, 4)      # Pausa entre cada resultado
DELAY_SCROLL = (1, 3)               # Pausa entre scrolls del feed

# Máximo de scrolls antes de parar (evita loops infinitos)
MAX_SCROLLS = 20

# ======================================================
# USER AGENTS (para simular diferentes navegadores)
# ======================================================
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]
