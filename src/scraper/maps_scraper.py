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


def scroll_feed(page: Page) -> int:
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

    for i in range(MAX_SCROLLS):
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

def extract_lead(page: Page, url: str, city: str) -> Lead | None:
    """
    Navega a la URL de un local en Google Maps, extrae los datos
    y aplica los filtros de cualificación.

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
    if rating < MIN_RATING:
        log.info(f"  ✗ {nombre} — rating {rating} (mín: {MIN_RATING})")
        return None

    # --- Filtro: Reseñas ---
    reviews = _get_reviews(page)
    if reviews < MIN_REVIEWS:
        log.info(f"  ✗ {nombre} — {reviews} reseñas (mín: {MIN_REVIEWS})")
        return None

    # --- Filtro: Web obligatoria ---
    website = _get_website(page)
    if not website:
        log.info(f"  ✗ {nombre} — sin página web")
        return None

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


def scrape_city(page: Page, city: str) -> list:
    """
    Ejecuta el scraping completo para una ciudad:
    buscar → scroll → recopilar URLs → extraer datos de cada una.
    """
    query = SEARCH_QUERY.format(city=city)
    url = f"https://www.google.com/maps/search/{quote_plus(query)}/"

    log.info(f"\n{'=' * 50}")
    log.info(f"CIUDAD: {city}")
    log.info(f"{'=' * 50}")

    page.goto(url, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(3000)

    # Aceptar cookies (solo la primera vez, pero no falla si ya se aceptaron)
    accept_cookies(page)

    # Scroll para cargar todos los resultados
    scroll_feed(page)

    # Recopilar URLs de los resultados
    place_urls = collect_urls(page)

    # Visitar cada resultado y extraer datos
    leads = []
    for i, place_url in enumerate(place_urls):
        log.info(f"  [{i + 1}/{len(place_urls)}] Procesando...")
        lead = extract_lead(page, place_url, city)
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


def save_leads(leads: list):
    """Guarda los leads en JSON y CSV dentro de data/."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # --- JSON ---
    json_path = DATA_DIR / "leads_raw.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([lead.to_dict() for lead in leads], f, ensure_ascii=False, indent=2)
    log.info(f"Guardado JSON: {json_path} ({len(leads)} leads)")

    # --- CSV ---
    csv_path = DATA_DIR / "leads_raw.csv"
    if leads:
        fields = list(leads[0].to_dict().keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for lead in leads:
                writer.writerow(lead.to_dict())
    log.info(f"Guardado CSV:  {csv_path} ({len(leads)} leads)")


# ==============================================================
# PUNTO DE ENTRADA
# ==============================================================

def run(cities: list | None = None, headless: bool = False):
    """
    Ejecuta el scraper completo.

    Args:
        cities:   Lista de ciudades (None = todas las de config.py)
        headless: True = navegador invisible / False = puedes verlo en pantalla
    """
    targets = cities or CITIES

    log.info(f"Iniciando scraper para {len(targets)} ciudades: {', '.join(targets)}")
    log.info(f"Filtros: ≥ {MIN_RATING}★, > {MIN_REVIEWS} reseñas, web obligatoria")
    log.info(f"Modo: {'headless' if headless else 'visible (verás el navegador)'}")

    all_leads = []

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
                city_leads = scrape_city(page, city)
                all_leads.extend(city_leads)
            except Exception as e:
                log.error(f"Error en {city}: {e}")
            _sleep(DELAY_BETWEEN_SEARCHES)

        context.close()
        browser.close()

    # Deduplicar y guardar
    all_leads = deduplicate(all_leads)
    save_leads(all_leads)

    # Resumen final
    log.info(f"\n{'=' * 50}")
    log.info(f"RESUMEN FINAL: {len(all_leads)} leads cualificados")
    log.info(f"{'=' * 50}")
    for city in targets:
        n = sum(1 for lead in all_leads if lead.ciudad == city)
        if n:
            log.info(f"  {city}: {n}")
    log.info(f"Datos guardados en: {DATA_DIR}/")

    return all_leads
