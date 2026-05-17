"""
Fase 1 — Scraper de Google Maps
Extrae clínicas de psicología cualificadas por ciudad.

Flujo:
  1. Buscar "Clínica de psicología en {ciudad}" en Google Maps
  2. Hacer scroll en el panel de resultados para cargar todos
  3. Recopilar las URLs de cada resultado
  4. Visitar cada URL y extraer datos (nombre, rating, reseñas, web, teléfono, dirección)
  5. Aplicar filtros de cualificación
  6. Guardar en JSON y CSV
"""

from __future__ import annotations

import json
import csv
import re
import random
import logging
import time
from pathlib import Path
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, Page

from src.scraper.config import (
    CITIES,
    SEARCH_QUERY,
    MIN_REVIEWS,
    MIN_RATING,
    DELAY_BETWEEN_SEARCHES,
    DELAY_BETWEEN_RESULTS,
    DELAY_SCROLL,
    MAX_SCROLLS,
    USER_AGENTS,
)
from src.models.lead import Lead

log = logging.getLogger("maps_scraper")

# Carpeta donde se guardan los datos (scrap-python/data/)
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


# ==============================================================
# HELPERS
# ==============================================================

def _sleep(delay_range: tuple):
    """Pausa aleatoria entre un rango de segundos (anti-bot)."""
    time.sleep(random.uniform(*delay_range))


def accept_cookies(page: Page):
    """
    Acepta el diálogo de cookies de Google.
    En España/UE aparece 'Aceptar todo' al entrar a Maps.
    """
    try:
        btn = page.get_by_role(
            "button",
            name=re.compile(r"Aceptar todo|Accept all", re.I),
        )
        btn.click(timeout=5000)
        log.info("Cookies aceptadas")
        page.wait_for_timeout(1000)
    except Exception:
        log.debug("No se encontró diálogo de cookies (ya aceptado o no presente)")


def scroll_feed(page: Page, max_scrolls: int = MAX_SCROLLS) -> int:
    """
    Hace scroll en el panel lateral de resultados de Google Maps
    hasta que no aparezcan más resultados nuevos.

    Retorna el número total de resultados cargados.
    """
    feed = page.locator('div[role="feed"]')
    try:
        feed.wait_for(state="visible", timeout=10000)
    except Exception:
        log.warning("Feed de resultados no encontrado")
        return 0

    prev_count = 0
    no_change = 0  # Contador de scrolls sin resultados nuevos

    for i in range(max_scrolls):
        count = feed.locator('a[href*="/maps/place/"]').count()

        if count == prev_count:
            no_change += 1
            # Si llevamos 3 scrolls sin cambios, paramos
            if no_change >= 3:
                break
        else:
            no_change = 0

        prev_count = count
        log.debug(f"  Scroll {i + 1}: {count} resultados")

        # Hacer scroll del último elemento a la vista
        feed.evaluate("""el => {
            const last = el.querySelector(':scope > div:last-child');
            if (last) last.scrollIntoView({behavior: 'smooth'});
            else el.scrollTop = el.scrollHeight;
        }""")
        _sleep(DELAY_SCROLL)

    log.info(f"  Feed cargado: {prev_count} resultados")
    return prev_count


def collect_urls(page: Page) -> list:
    """
    Recoge todas las URLs de locales del feed de resultados.
    Cada resultado tiene un <a> con href tipo /maps/place/NombreDelSitio/...
    """
    feed = page.locator('div[role="feed"]')
    links = feed.locator('a[href*="/maps/place/"]')
    count = links.count()

    urls = []
    seen = set()
    for i in range(count):
        href = links.nth(i).get_attribute("href")
        if href and href not in seen:
            seen.add(href)
            urls.append(href)

    log.info(f"  URLs únicas recopiladas: {len(urls)}")
    return urls


# ==============================================================
# EXTRACTORES — Cada función intenta varias estrategias
# ==============================================================

def _get_rating(page: Page) -> float:
    """Extrae la puntuación (estrellas) de la ficha del local."""
    # Estrategia 1: Clase fontDisplayLarge (la más habitual en Google Maps)
    for selector in ["div.fontDisplayLarge", "span.fontDisplayLarge"]:
        try:
            text = page.locator(selector).first.inner_text(timeout=2000)
            return float(text.strip().replace(",", "."))
        except Exception:
            continue

    # Estrategia 2: aria-label con info de estrellas
    try:
        el = page.locator('span[role="img"]').first
        label = el.get_attribute("aria-label", timeout=2000) or ""
        m = re.search(r"([\d,\.]+)", label)
        if m:
            return float(m.group(1).replace(",", "."))
    except Exception:
        pass

    return 0.0


def _get_reviews(page: Page) -> int:
    """Extrae el número de reseñas."""
    # Estrategia 1: Botón del gráfico de reseñas
    try:
        el = page.locator('button[jsaction*="reviewChart"]').first
        text = el.inner_text(timeout=2000)
        # En España los miles van con punto (1.234) — limpiar antes de parsear
        m = re.search(r"(\d[\d.]*)", text)
        if m:
            return int(m.group(1).replace(".", ""))
    except Exception:
        pass

    # Estrategia 2: aria-label del botón de reseñas
    try:
        el = page.locator(
            'button[aria-label*="reseña"], button[aria-label*="review"]'
        ).first
        label = el.get_attribute("aria-label", timeout=2000) or ""
        m = re.search(r"(\d[\d.]*)", label)
        if m:
            return int(m.group(1).replace(".", ""))
    except Exception:
        pass

    return 0


def _get_website(page: Page) -> str:
    """Extrae la URL de la web de la clínica."""
    try:
        el = page.locator('a[data-item-id="authority"]').first
        return el.get_attribute("href", timeout=3000) or ""
    except Exception:
        return ""


def _get_phone(page: Page) -> str:
    """Extrae el teléfono de contacto."""
    try:
        el = page.locator('button[data-item-id^="phone:"]').first
        return el.inner_text(timeout=2000).strip()
    except Exception:
        return ""


def _get_address(page: Page) -> str:
    """Extrae la dirección completa."""
    try:
        el = page.locator('button[data-item-id="address"]').first
        return el.inner_text(timeout=2000).strip()
    except Exception:
        return ""


# ==============================================================
# LÓGICA PRINCIPAL
# ==============================================================

def extract_lead(
    page: Page,
    url: str,
    city: str,
    min_rating: float = MIN_RATING,
    min_reviews: int = MIN_REVIEWS,
    require_website: str = "required",
) -> Lead | None:
    """
    Navega a la URL de un local en Google Maps, extrae los datos
    y aplica los filtros de cualificación.

    require_website: 'required' = solo con web | 'none' = solo sin web | 'any' = todos
    Retorna un Lead si cualifica, o None si no pasa los filtros.
    """
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
    except Exception as e:
        log.warning(f"  Error cargando URL: {e}")
        return None

    # Esperar a que la página renderice el contenido dinámico
    page.wait_for_timeout(2000)

    # --- Nombre (obligatorio) ---
    try:
        nombre = page.locator("h1").first.inner_text(timeout=5000)
    except Exception:
        log.warning("  No se pudo extraer el nombre")
        return None

    # --- Filtro: Puntuación ---
    rating = _get_rating(page)
    if rating < min_rating:
        log.info(f"  ✗ {nombre} — rating {rating} (mín: {min_rating})")
        return None

    # --- Filtro: Reseñas ---
    reviews = _get_reviews(page)
    if reviews < min_reviews:
        log.info(f"  ✗ {nombre} — {reviews} reseñas (mín: {min_reviews})")
        return None

    # --- Filtro: Sitio web ---
    website = _get_website(page)
    if require_website == "required" and not website:
        log.info(f"  ✗ {nombre} — sin página web")
        return None
    elif require_website == "none" and website:
        log.info(f"  ✗ {nombre} — tiene web (filtro: solo sin web)")
        return None
    # require_website == 'any' → no filter

    # --- Datos opcionales ---
    telefono = _get_phone(page)
    direccion = _get_address(page)

    lead = Lead(
        nombre=nombre,
        ciudad=city,
        direccion=direccion,
        telefono=telefono,
        url=website,
        puntuacion=rating,
        resenas=reviews,
    )
    log.info(f"  ✓ {nombre} | {rating}★ | {reviews} rev | {city}")
    return lead


def scrape_city(
    page: Page,
    city: str,
    search_query: str = SEARCH_QUERY,
    min_rating: float = MIN_RATING,
    min_reviews: int = MIN_REVIEWS,
    require_website: str = "required",
    max_scrolls: int = MAX_SCROLLS,
) -> list:
    """
    Ejecuta el scraping completo para una ciudad:
    buscar → scroll → recopilar URLs → extraer datos de cada una.
    """
    query = search_query.format(city=city)
    url = f"https://www.google.com/maps/search/{quote_plus(query)}/"

    log.info(f"\n{'=' * 50}")
    log.info(f"CIUDAD: {city}")
    log.info(f"{'=' * 50}")

    page.goto(url, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(3000)

    # Aceptar cookies (solo la primera vez, pero no falla si ya se aceptaron)
    accept_cookies(page)

    # Scroll para cargar todos los resultados
    scroll_feed(page, max_scrolls)

    # Recopilar URLs de los resultados
    place_urls = collect_urls(page)

    # Visitar cada resultado y extraer datos
    leads = []
    for i, place_url in enumerate(place_urls):
        log.info(f"  [{i + 1}/{len(place_urls)}] Procesando...")
        lead = extract_lead(page, place_url, city, min_rating, min_reviews, require_website)
        if lead:
            leads.append(lead)
        _sleep(DELAY_BETWEEN_RESULTS)

    log.info(f"  → {city}: {len(leads)} leads cualificados de {len(place_urls)} resultados")
    return leads


# ==============================================================
# DEDUPLICACIÓN Y GUARDADO
# ==============================================================

def deduplicate(leads: list) -> list:
    """Elimina leads duplicados por nombre + dirección."""
    seen = set()
    unique = []
    for lead in leads:
        key = lead.dedup_key
        if key not in seen:
            seen.add(key)
            unique.append(lead)

    removed = len(leads) - len(unique)
    if removed:
        log.info(f"Duplicados eliminados: {removed}")
    return unique


def load_existing_leads() -> list:
    """Carga leads existentes de leads_raw.json para evitar duplicados."""
    json_path = DATA_DIR / "leads_raw.json"
    if not json_path.exists():
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        leads = []
        for d in data:
            leads.append(Lead(
                nombre=d["nombre"],
                ciudad=d["ciudad"],
                direccion=d.get("direccion", ""),
                telefono=d.get("telefono", ""),
                url=d.get("url", ""),
                puntuacion=d.get("puntuacion", 0),
                resenas=d.get("resenas", 0),
            ))
        log.info(f"Leads existentes cargados: {len(leads)}")
        return leads
    except Exception as e:
        log.warning(f"No se pudieron cargar leads existentes: {e}")
        return []


def save_leads(leads: list, run_id: str | None = None):
    """Guarda los leads en JSON y CSV dentro de data/.
    Si se indica run_id, guarda también una copia con timestamp en data/runs/.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    data = [lead.to_dict() for lead in leads]

    # --- JSON principal (siempre) ---
    json_path = DATA_DIR / "leads_raw.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"Guardado JSON: {json_path} ({len(leads)} leads)")

    # --- CSV principal (siempre) ---
    csv_path = DATA_DIR / "leads_raw.csv"
    if leads:
        fields = list(leads[0].to_dict().keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for lead in leads:
                writer.writerow(lead.to_dict())
    log.info(f"Guardado CSV:  {csv_path} ({len(leads)} leads)")

    # --- Copia con timestamp (si hay run_id) ---
    if run_id:
        runs_dir = DATA_DIR / "runs"
        runs_dir.mkdir(exist_ok=True)
        ts_json = runs_dir / f"{run_id}-raw.json"
        ts_csv  = runs_dir / f"{run_id}-raw.csv"
        with open(ts_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if leads:
            with open(ts_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for lead in leads:
                    writer.writerow(lead.to_dict())
        log.info(f"Copia run guardada: {ts_json}")


# ==============================================================
# PUNTO DE ENTRADA
# ==============================================================

def run(cities: list | None = None, headless: bool = False, profile: dict | None = None):
    """
    Ejecuta el scraper completo.
    Acumula leads existentes de leads_raw.json para no repetir.

    Args:
        cities:   Lista de ciudades (None = usa perfil o config.py)
        headless: True = navegador invisible / False = puedes verlo en pantalla
        profile:  Dict con parámetros del personalizador de scrap (opcional)
    """
    cfg = profile or {}
    _raw_ciudades = cfg.get("ciudades")
    if isinstance(_raw_ciudades, list):
        _parsed_ciudades = _raw_ciudades or None
    elif isinstance(_raw_ciudades, str):
        _parsed_ciudades = json.loads(_raw_ciudades) or None
    else:
        _parsed_ciudades = None
    targets = cities or _parsed_ciudades or CITIES
    search_query = cfg.get("search_query", SEARCH_QUERY)
    min_rating = float(cfg.get("min_rating", MIN_RATING))
    min_reviews = int(cfg.get("min_reviews", MIN_REVIEWS))
    require_website = cfg.get("require_website", "required")
    max_scrolls = int(cfg.get("max_scrolls", MAX_SCROLLS))

    # Cargar leads existentes para no repetir
    existing = load_existing_leads()
    existing_keys = {lead.dedup_key for lead in existing}
    log.info(f"Leads existentes: {len(existing)} (se saltarán duplicados)")

    log.info(f"Iniciando scraper para {len(targets)} ciudades: {', '.join(targets)}")
    web_label = {"required": "solo con web", "none": "solo sin web", "any": "todas"}.get(require_website, require_website)
    log.info(f"Filtros: ≥ {min_rating}★, > {min_reviews} reseñas, web: {web_label}")
    log.info(f"Modo: {'headless' if headless else 'visible (verás el navegador)'}")

    new_leads = []

    with sync_playwright() as p:
        # Lanzar navegador Chromium
        browser = p.chromium.launch(headless=headless)

        # Crear contexto con user-agent aleatorio y configuración española
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 900},
            locale="es-ES",
            geolocation={"latitude": 40.4168, "longitude": -3.7038},
            permissions=["geolocation"],
        )
        page = context.new_page()

        for city in targets:
            try:
                city_leads = scrape_city(page, city, search_query, min_rating, min_reviews, require_website, max_scrolls)
                # Filtrar los que ya existen
                for lead in city_leads:
                    if lead.dedup_key not in existing_keys:
                        new_leads.append(lead)
                        existing_keys.add(lead.dedup_key)
                    else:
                        log.info(f"  ⊘ {lead.nombre} — ya existe, saltando")
            except Exception as e:
                log.error(f"Error en {city}: {e}")
            _sleep(DELAY_BETWEEN_SEARCHES)

        context.close()
        browser.close()

    # Combinar existentes + nuevos y guardar
    all_leads = existing + deduplicate(new_leads)
    save_leads(all_leads, run_id=cfg.get("run_id"))

    # Resumen final
    log.info(f"\n{'=' * 50}")
    log.info(f"RESUMEN FINAL")
    log.info(f"{'=' * 50}")
    log.info(f"Leads previos:     {len(existing)}")
    log.info(f"Leads nuevos:      {len(new_leads)}")
    log.info(f"Total acumulado:   {len(all_leads)}")
    for city in targets:
        n = sum(1 for lead in all_leads if lead.ciudad == city)
        if n:
            log.info(f"  {city}: {n}")
    log.info(f"Datos guardados en: {DATA_DIR}/")

    return all_leads
