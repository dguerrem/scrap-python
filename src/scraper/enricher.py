"""
Fase 2 — Enriquecimiento de Leads
Visita la web de cada clínica extraída en Fase 1 y:
  1. Busca el "Aviso Legal" / "Política de Privacidad"
  2. Extrae el nombre del Responsable/Titular
  3. Extrae emails del HTML completo
  4. Clasifica emails en genéricos vs directos
  5. Guarda leads enriquecidos en JSON y CSV
"""

from __future__ import annotations

import json
import csv
import os
import re
import random
import logging
import time
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, Page

from src.scraper.config import USER_AGENTS
from src.models.lead import Lead
from src.scraper.privacy import mask, show

log = logging.getLogger("enricher")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# Delays para no saturar las webs de las clínicas
DELAY_BETWEEN_SITES = (2, 5)
PAGE_TIMEOUT = 15000  # ms

# ======================================================
# EMAILS — Extracción y clasificación
# ======================================================

# Regex para encontrar emails en HTML
EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# Prefijos que indican un email genérico (no personal)
GENERIC_PREFIXES = {
    "info", "contacto", "hola", "hello", "contact",
    "admin", "administracion", "recepcion", "consultas",
    "citas", "reservas", "atencion", "soporte", "support",
    "web", "webmaster", "noreply", "no-reply",
    "clinica", "centro", "center", "gabinete", "consulta",
    "secretaria", "agenda", "equipo", "general",
}


def _classify_email(email: str) -> str:
    """
    Clasifica un email como 'directo' o 'generico'.
    Retorna 'directo' si el prefijo NO está en la lista de genéricos.
    """
    prefix = email.split("@")[0].lower().strip()
    if prefix in GENERIC_PREFIXES:
        return "generico"
    return "directo"


def _extract_emails(html: str, domain: str) -> dict:
    """
    Extrae todos los emails del HTML y los clasifica.
    Prioriza emails del mismo dominio que la web.

    Retorna: {"directo": "...", "generico": "..."}
    """
    raw_emails = set(EMAIL_REGEX.findall(html))

    # Filtrar basura (imágenes, archivos, placeholders, etc.)
    filtered = []
    for email in raw_emails:
        lower = email.lower()
        # Descartar extensiones de archivo que coinciden con el regex
        if any(lower.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]):
            continue
        # Descartar emails con dominios de tracking/analytics
        if any(d in lower for d in ["sentry.io", "googleapis", "cloudflare", "wixpress"]):
            continue
        # Descartar emails placeholder / ejemplo
        if any(p in lower for p in ["usuario@dominio", "example@", "ejemplo@",
                                      "nombre@dominio", "nombre@email",
                                      "tu@tu", "your@",
                                      "email@email", "test@test", "user@user",
                                      "xxxxx"]):
            continue
        # Limpiar espacios URL-encoded (%20) al principio
        email = email.lstrip("%20 ")
        if not email or "@" not in email:
            continue
        filtered.append(email)

    # Separar por tipo
    directos = []
    genericos = []
    for email in filtered:
        if _classify_email(email) == "directo":
            directos.append(email)
        else:
            genericos.append(email)

    # Priorizar emails del dominio de la clínica
    domain_clean = domain.lower().replace("www.", "")
    directos_domain = [e for e in directos if domain_clean in e.lower()]
    genericos_domain = [e for e in genericos if domain_clean in e.lower()]

    return {
        "directo": directos_domain[0] if directos_domain else (directos[0] if directos else ""),
        "generico": genericos_domain[0] if genericos_domain else (genericos[0] if genericos else ""),
    }


# ======================================================
# AVISO LEGAL — Extracción del director/responsable
# ======================================================

# Textos de enlace que pueden llevar al aviso legal
LEGAL_LINK_PATTERNS = [
    "aviso legal",
    "aviso-legal",
    "avisolegal",
    "politica de privacidad",
    "política de privacidad",
    "privacidad",
    "legal",
    "condiciones",
    "proteccion de datos",
    "protección de datos",
    "datos personales",
    "lopd",
    "rgpd",
]

# Palabras clave que preceden al nombre del responsable en textos legales
RESPONSIBLE_PATTERNS = [
    # "Responsable: Juan García López" o "Responsable del tratamiento: ..."
    r"(?:responsable(?:\s+del\s+tratamiento)?)\s*[:;]\s*(.{3,120})",
    # "Titular: ..." / "Titular del sitio web: ..."
    r"(?:titular(?:\s+del\s+sitio\s*(?:web)?)?)\s*[:;]\s*(.{3,120})",
    # "Identidad: ..."
    r"(?:identidad(?:\s+del\s+responsable)?)\s*[:;]\s*(.{3,120})",
    # "Denominación social: ..." / "Denominación: ..."
    r"(?:denominaci[oó]n(?:\s+social)?)\s*[:;]\s*(.{3,120})",
    # "Razón social: ..."
    r"(?:raz[oó]n\s+social)\s*[:;]\s*(.{3,120})",
    # "Nombre del responsable: ..."
    r"(?:nombre\s+(?:del\s+)?responsable)\s*[:;]\s*(.{3,120})",
    # "Propietario: ..."
    r"(?:propietario)\s*[:;]\s*(.{3,120})",
]

# Regex para detectar NIF/CIF/DNI (indicador de que estamos en la zona correcta)
NIF_REGEX = re.compile(r"\b[A-Z]?\d{7,8}[A-Z]?\b")


def _clean_name(raw: str) -> str:
    """Limpia el nombre extraído del aviso legal."""
    # Cortar en delimitadores que indican fin del nombre (case-insensitive)
    cut_markers = [
        "cif:", "cif :", "cif ", "cif/", "cif b", "cif a",
        "nif:", "nif :", "nif ", "nif/",
        "dni:", "dni :", "dni ", "dni/",
        "domicilio", "dirección", "direccion",
        "actividad", "inscrita", "finalidad", "gestión", "gestion",
        "ha contratado", "de los contenidos", "y de todos", "en adelante",
        "nombre comercial", "http://", "https://",
    ]
    raw_lower = raw.lower()
    for sep in cut_markers:
        idx = raw_lower.find(sep)
        if idx > 0:
            raw = raw[:idx]
            raw_lower = raw.lower()
    # Quitar NIF/CIF si está pegado al nombre
    name = NIF_REGEX.sub("", raw)
    # Quitar caracteres extra
    name = re.sub(r"[,;.\-–—]$", "", name.strip())
    # Quitar "con NIF", "con CIF", "con DNI" y lo que siga
    name = re.sub(r"\s+con\s+(?:NIF|CIF|DNI).*$", "", name, flags=re.IGNORECASE)
    # Quitar "(en adelante...)" y similares
    name = re.sub(r"\(.*?\)", "", name)
    # Quitar prefijos sueltos de contexto HTML ("¿Quiénes somos?", etc.)
    name = re.sub(r"^[¿?¡!].*?[.?!]\s*", "", name)
    # Rechazar si es una URL (falso positivo)
    if name.startswith(("http://", "https://", "www.")):
        return ""
    # Rechazar si parece una frase (no un nombre propio/sociedad)
    words = name.split()
    if len(words) > 6:
        return ""
    # Rechazar placeholders y basura evidente
    name_lower = name.lower()
    if any(x in name_lower for x in ["xxx", "ver datos", "encabezamiento",
                                       "rellenar", "placeholder"]):
        return ""
    # Limitar longitud (si es demasiado largo, probablemente pillamos basura)
    name = name.strip()
    if len(name) > 80:
        name = name[:80].rsplit(" ", 1)[0]
    return name


def _extract_director_from_text(text: str) -> tuple:
    """
    Busca el nombre del responsable/titular en el texto del aviso legal.
    Retorna (director, sociedad).
    """
    director = ""
    sociedad = ""

    # Normalizar texto: quitar saltos de línea múltiples
    clean_text = re.sub(r"\s+", " ", text)

    for pattern in RESPONSIBLE_PATTERNS:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            name = _clean_name(raw)

            if not name or len(name) < 3:
                continue

            # Heurística: si contiene "S.L.", "S. L.", "S.A.", "SLP" → es sociedad
            # Requiere punto después de S para no matchear "Saavedra", "Sanchez"
            if re.search(r"\bS\.\s*L\.?\s*P?\.?|\bS\.\s*A\.?|\bS\.\s*C\.?|\bSLP\b|\bSLL\b|\bSOCIEDAD\b", name):
                sociedad = name
            else:
                director = name

            # Si ya tenemos director, paramos
            if director:
                break

    return director, sociedad


def _find_legal_links(page: Page) -> list:
    """
    Busca en la página enlaces que lleven al aviso legal / política de privacidad.
    Retorna lista de URLs absolutas.
    """
    links = []
    all_anchors = page.locator("a[href]")
    count = all_anchors.count()

    for i in range(count):
        try:
            anchor = all_anchors.nth(i)
            text = anchor.inner_text(timeout=1000).lower().strip()
            href = anchor.get_attribute("href") or ""

            # Comprobar si el texto o href coincide con patrones legales
            text_and_href = f"{text} {href.lower()}"
            for pattern in LEGAL_LINK_PATTERNS:
                if pattern in text_and_href:
                    # Construir URL absoluta
                    full_url = urljoin(page.url, href)
                    if full_url not in links:
                        links.append(full_url)
                    break
        except Exception:
            continue

    return links


def _extract_director(page: Page, base_url: str) -> tuple:
    """
    Intenta extraer el nombre del director/responsable:
    1. Busca enlaces de aviso legal en la página actual
    2. Visita cada enlace y busca el nombre del responsable
    3. Si no encuentra enlaces, busca en el HTML de la propia página

    Retorna (director, sociedad).
    """
    # Primero: buscar en la página principal (a veces el aviso está en el footer)
    main_html = page.content()
    main_text = page.inner_text("body", timeout=5000)
    director, sociedad = _extract_director_from_text(main_text)
    if director:
        return director, sociedad

    # Segundo: buscar enlaces de aviso legal y visitarlos
    legal_urls = _find_legal_links(page)
    log.debug(f"    Enlaces legales encontrados: {len(legal_urls)}")

    for legal_url in legal_urls[:3]:  # Máximo 3 enlaces para no tardar demasiado
        try:
            page.goto(legal_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            page.wait_for_timeout(1500)
            legal_text = page.inner_text("body", timeout=5000)
            director, sociedad = _extract_director_from_text(legal_text)
            if director or sociedad:
                log.debug(f"    Encontrado en: {legal_url}")
                return director, sociedad
        except Exception as e:
            log.debug(f"    Error visitando {legal_url}: {e}")
            continue

    return director, sociedad


# ======================================================
# LÓGICA PRINCIPAL
# ======================================================

def enrich_lead(page: Page, lead_data: dict) -> dict:
    """
    Enriquece un lead visitando su web:
    - Extrae director del aviso legal
    - Extrae emails
    - Actualiza el estado a 'Enriched' si encuentra datos útiles
    """
    url = lead_data.get("url", "")
    nombre = lead_data.get("nombre", "")

    if not url:
        log.info(f"  ✗ {mask(nombre)} — sin URL")
        return lead_data

    # Extraer dominio para priorizar emails
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
    except Exception:
        domain = ""

    # Navegar a la web de la clínica
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        page.wait_for_timeout(2000)
    except Exception as e:
        log.info(f"  ✗ {mask(nombre)} — error cargando web: {e}")
        return lead_data

    # --- Extraer emails del HTML completo ---
    try:
        html = page.content()
        emails = _extract_emails(html, domain)
        lead_data["email_directo"] = emails["directo"]
        lead_data["email_generico"] = emails["generico"]
    except Exception as e:
        log.debug(f"    Error extrayendo emails: {e}")

    # --- Extraer director del aviso legal ---
    try:
        director, sociedad = _extract_director(page, url)
        lead_data["director"] = director
        lead_data["sociedad"] = sociedad
    except Exception as e:
        log.debug(f"    Error extrayendo director: {e}")

    # --- Actualizar estado ---
    has_director = bool(lead_data.get("director"))
    has_email = bool(lead_data.get("email_directo") or lead_data.get("email_generico"))

    if has_director or has_email:
        lead_data["estado"] = "Enriched"
        parts = [f"dir={show(lead_data.get('director'))}"]
        if lead_data.get("email_directo"):
            parts.append(f"email={show(lead_data['email_directo'])}")
        elif lead_data.get("email_generico"):
            parts.append(f"email_gen={show(lead_data['email_generico'])}")
        else:
            parts.append("email=no")
        if lead_data.get("sociedad"):
            parts.append(f"soc={mask(lead_data['sociedad'])}")
        log.info(f"  ✓ {mask(nombre)} — {' | '.join(parts)}")
    else:
        log.info(f"  ○ {mask(nombre)} — sin datos de enriquecimiento")

    return lead_data


def save_enriched(leads: list, run_id: str | None = None):
    """Guarda los leads enriquecidos en JSON y CSV.
    Si se indica run_id, guarda también una copia con timestamp en data/runs/.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # JSON principal
    json_path = DATA_DIR / "leads_enriched.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2)
    log.info(f"Guardado JSON: {json_path}")

    # CSV principal
    csv_path = DATA_DIR / "leads_enriched.csv"
    if leads:
        fields = list(leads[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for lead in leads:
                writer.writerow(lead)
    log.info(f"Guardado CSV:  {csv_path}")

    # Copia con timestamp
    if run_id:
        runs_dir = DATA_DIR / "runs"
        runs_dir.mkdir(exist_ok=True)
        ts_json = runs_dir / f"{run_id}-enriched.json"
        ts_csv  = runs_dir / f"{run_id}-enriched.csv"
        with open(ts_json, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
        if leads:
            with open(ts_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for lead in leads:
                    writer.writerow(lead)
        log.info(f"Copia run guardada: {ts_json}")


def _new_browser_page(p, headless: bool):
    """Crea contexto y página con user-agent aleatorio y locale español."""
    browser = p.chromium.launch(headless=headless)
    context = browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1280, "height": 900},
        locale="es-ES",
    )
    return browser, context, context.new_page()


def _run_from_db(limit: int | None = None, headless: bool = False) -> list:
    """
    Enriquece leyendo los leads de la BD y escribiendo el resultado de vuelta.

    Camino usado en cloud cuando no existe `leads_raw.json` (modo 'enricher'
    suelto). Cada lead se guarda nada más procesarlo, así una interrupción
    no pierde el trabajo ya hecho.
    """
    from src.crm.db import get_leads_to_enrich, update_lead_enrichment

    leads = get_leads_to_enrich(limit=limit)
    if not leads:
        log.warning("No hay leads pendientes de enriquecer en la BD.")
        return []

    log.info(f"Enriqueciendo {len(leads)} leads desde la BD")

    with sync_playwright() as p:
        browser, context, page = _new_browser_page(p, headless)

        for i, lead in enumerate(leads):
            # Log sin datos personales: los logs de Actions son públicos
            log.info(f"  [{i + 1}/{len(leads)}] lead #{lead['id']}")
            try:
                enrich_lead(page, lead)
                update_lead_enrichment(
                    lead["id"],
                    lead.get("director", ""),
                    lead.get("email_directo", ""),
                    lead.get("email_generico", ""),
                    lead.get("sociedad", ""),
                )
            except Exception as e:
                log.warning(f"    Error procesando lead #{lead['id']}: {e}")
            time.sleep(random.uniform(*DELAY_BETWEEN_SITES))

        context.close()
        browser.close()

    con_director = sum(1 for l in leads if l.get("director"))
    con_directo = sum(1 for l in leads if l.get("email_directo"))
    con_generico = sum(1 for l in leads if l.get("email_generico"))

    log.info(f"\n{'=' * 50}")
    log.info("RESUMEN ENRIQUECIMIENTO (BD)")
    log.info(f"{'=' * 50}")
    log.info(f"Total procesados:     {len(leads)}")
    log.info(f"Con director:         {con_director}")
    log.info(f"Con email directo:    {con_directo}")
    log.info(f"Con email genérico:   {con_generico}")

    return leads


def run(limit: int | None = None, headless: bool = False, run_id: str | None = None):
    """
    Ejecuta el enriquecimiento sobre los leads de Fase 1.

    Fuente de datos:
      · Si existe `data/leads_raw.json` → se usa (local y modo 'pipeline' en
        cloud, donde el scraper acaba de generarlo con los leads frescos).
      · Si no existe y hay Turso configurado → se leen de la BD (modo
        'enricher' suelto en Actions, que arranca de checkout limpio).

    Args:
        limit:    Número máximo de leads a enriquecer (None = todos)
        headless: True = navegador invisible
        run_id:   Identificador de la ejecución para guardar copia timestamped
    """
    # Cargar leads de Fase 1
    json_path = DATA_DIR / "leads_raw.json"
    if not json_path.exists():
        if os.environ.get("TURSO_DATABASE_URL"):
            return _run_from_db(limit=limit, headless=headless)
        log.error(f"No se encontró {json_path}. Ejecuta primero la Fase 1 (run_scraper.py).")
        return []

    with open(json_path, "r", encoding="utf-8") as f:
        leads = json.load(f)

    if limit:
        leads = leads[:limit]

    log.info(f"Enriqueciendo {len(leads)} leads desde {json_path}")
    log.info(f"Modo: {'headless' if headless else 'visible (verás el navegador)'}")

    with sync_playwright() as p:
        browser, context, page = _new_browser_page(p, headless)

        for i, lead in enumerate(leads):
            log.info(f"\n  [{i + 1}/{len(leads)}] {mask(lead['nombre'])}")

            # Asegurar campos nuevos existen
            lead.setdefault("director", "")
            lead.setdefault("email_directo", "")
            lead.setdefault("email_generico", "")
            lead.setdefault("sociedad", "")

            enrich_lead(page, lead)
            time.sleep(random.uniform(*DELAY_BETWEEN_SITES))

        context.close()
        browser.close()

    # Guardar
    save_enriched(leads, run_id=run_id)

    # Resumen
    enriched = sum(1 for l in leads if l.get("estado") == "Enriched")
    with_director = sum(1 for l in leads if l.get("director"))
    with_direct_email = sum(1 for l in leads if l.get("email_directo"))
    with_generic_email = sum(1 for l in leads if l.get("email_generico"))

    log.info(f"\n{'=' * 50}")
    log.info(f"RESUMEN ENRIQUECIMIENTO")
    log.info(f"{'=' * 50}")
    log.info(f"Total procesados:     {len(leads)}")
    log.info(f"Enriquecidos:         {enriched}")
    log.info(f"Con director:         {with_director}")
    log.info(f"Con email directo:    {with_direct_email}")
    log.info(f"Con email genérico:   {with_generic_email}")
    log.info(f"Datos en: {DATA_DIR}/")

    return leads
