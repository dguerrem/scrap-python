"""
Configuración del scraper — PsycoLead-Scraper
Edita este archivo para ajustar ciudades, filtros y delays.
"""

# ======================================================
# LOCALIDADES OBJETIVO
# ======================================================
LOCALITIES_BY_PROVINCE = {
    "A Coruña": (
        "A Coruña", "Ames", "Arteixo", "Boiro", "Cambre", "Carballo",
        "Culleredo", "Ferrol", "Narón", "Oleiros", "Ribeira",
        "Santiago de Compostela",
    ),
    "Asturias": ("Avilés", "Gijón", "Oviedo"),
    "Barcelona": ("Barcelona",),
    "Cantabria": (
        "Camargo", "Castro-Urdiales", "El Astillero", "Laredo",
        "Los Corrales de Buelna", "Piélagos", "Santa Cruz de Bezana",
        "Santander", "Santoña", "Torrelavega",
    ),
    "León": (
        "Astorga", "Bembibre", "Cacabelos", "Camponaraya", "Fabero",
        "La Bañeza", "La Robla", "León", "Ponferrada",
        "San Andrés del Rabanedo", "Sariegos", "Valencia de Don Juan",
        "Valverde de la Virgen", "Villaquilambre", "Villablino",
    ),
    "Lugo": ("Lugo",),
    "Madrid": ("Madrid",),
    "Málaga": ("Málaga",),
    "Murcia": ("Murcia",),
    "Ourense": ("Ourense",),
    "Palencia": (
        "Aguilar de Campoo", "Cervera de Pisuerga", "Dueñas", "Grijota",
        "Guardo", "Herrera de Pisuerga", "Palencia", "Saldaña",
        "Venta de Baños", "Villamuriel de Cerrato",
    ),
    "Palmas, Las": ("Las Palmas de Gran Canaria",),
    "Pontevedra": (
        "A Estrada", "Cangas do Morrazo", "Lalín", "Marín", "Moaña",
        "Nigrán", "O Porriño", "Ponteareas", "Pontevedra", "Redondela", "Vigo",
        "Vilagarcía de Arousa",
    ),
    "Salamanca": (
        "Alba de Tormes", "Béjar", "Carbajosa de la Sagrada",
        "Ciudad Rodrigo", "Doñinos de Salamanca", "Guijuelo",
        "Peñaranda de Bracamonte", "Salamanca", "Santa Marta de Tormes",
        "Villamayor",
    ),
    "Sevilla": ("Sevilla",),
    "Valencia": ("Valencia",),
    "Zamora": (
        "Benavente", "Burganes de Valverde", "Fermoselle",
        "Morales del Vino", "Puebla de Sanabria", "Toro", "Villalpando",
        "Zamora",
    ),
    "Zaragoza": ("Zaragoza",),
    "Baleares, Illes": ("Palma de Mallorca",),
    "Bizkaia": ("Bilbao",),
}

CITIES = [
    city
    for localities in LOCALITIES_BY_PROVINCE.values()
    for city in localities
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
