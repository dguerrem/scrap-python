"""
Test de la Fase 4 — exposicion de datos y fallos silenciosos.

  RIESGO-A  los logs de CI no deben publicar nombres, emails ni directores
  RIESGO-B  los artifacts solo se suben si los datos NO llegaron a Turso
  RIESGO-D  un scraping bloqueado debe terminar en rojo, no en verde

Uso:  python tests/test_fase4_riesgos.py
"""
import importlib
import logging
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ok = True


def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"  OK   {label}")
    else:
        ok = False
        print(f"  FAIL {label}  {detail}")


def cargar_privacy(en_ci: bool):
    """Reimporta el modulo simulando (o no) un runner de GitHub Actions."""
    if en_ci:
        os.environ["CI"] = "true"
    else:
        os.environ.pop("CI", None)
        os.environ.pop("GITHUB_ACTIONS", None)
    import src.scraper.privacy as privacy
    return importlib.reload(privacy)


NOMBRE = "Centro de Psicologia Alameda"
EMAIL = "maria.lopez@psicologiaalameda.es"
DIRECTOR = "Maria Lopez Garcia"

print("\n1) En LOCAL no se oculta nada (los logs sirven para depurar)")
p = cargar_privacy(en_ci=False)
check("mask() devuelve el nombre real", p.mask(NOMBRE) == NOMBRE, p.mask(NOMBRE))
check("show() devuelve el email real", p.show(EMAIL) == EMAIL, p.show(EMAIL))
check("show() vacio -> 'no'", p.show("") == "no", p.show(""))

print("\n2) En CI se oculta todo dato personal")
p = cargar_privacy(en_ci=True)
m = p.mask(NOMBRE)
check("mask() no contiene el nombre", NOMBRE not in m, m)
check("mask() produce un hash corto", re.fullmatch(r"<[0-9a-f]{6}>", m), m)
check("mask() es estable (misma clinica, mismo codigo)", m == p.mask(NOMBRE))
check("mask() distingue clinicas distintas", p.mask("Otra Clinica") != m)
check("show() con email -> 'si', sin filtrarlo", p.show(EMAIL) == "sí", p.show(EMAIL))
check("show() sin valor -> 'no'", p.show("") == "no")
check("mask() de vacio no inventa hash", p.mask("") == "")

print("\n3) Red de seguridad: ningun email sobrevive al filtro")
registros = []


class Captura(logging.Handler):
    def emit(self, record):
        registros.append(self.format(record))


log = logging.getLogger("test_redaccion")
log.handlers.clear()
log.propagate = False
h = Captura()
h.setFormatter(logging.Formatter("%(message)s"))
h.addFilter(p.RedactEmailsFilter())
log.addHandler(h)
log.setLevel(logging.INFO)

log.info(f"Error procesando: SMTP rejected {EMAIL} for domain")
log.info("Contacto: info@clinica.com y tambien gerencia@otra-clinica.co.uk")
log.info("Sin datos personales aqui")

check("email en texto de excepcion redactado", EMAIL not in registros[0], registros[0])
check("multiples emails redactados",
      "@clinica.com" not in registros[1] and "@otra-clinica.co.uk" not in registros[1],
      registros[1])
check("cuenta 2 marcadores", registros[1].count("<email>") == 2, registros[1])
check("las lineas limpias no se tocan", registros[2] == "Sin datos personales aqui")

print("\n4) Las lineas de log reales del scraper y el enricher estan saneadas")
fuentes = {
    "maps_scraper.py": (ROOT / "src/scraper/maps_scraper.py").read_text(encoding="utf-8"),
    "enricher.py": (ROOT / "src/scraper/enricher.py").read_text(encoding="utf-8"),
}
PELIGROSAS = [
    (r"log\.info\(f\"[^\"]*\{nombre\}", "{nombre} sin mask()"),
    (r"log\.info\(f\"[^\"]*\{lead\.nombre\}", "{lead.nombre} sin mask()"),
    (r"log\.info\(f\"[^\"]*\{lead\['nombre'\]\}", "{lead['nombre']} sin mask()"),
    (r"lead_data\['email_directo'\]\}", "email_directo en crudo"),
    (r"lead_data\['director'\]\}", "director en crudo"),
]
for fichero, codigo in fuentes.items():
    for patron, descripcion in PELIGROSAS:
        hits = re.findall(patron, codigo)
        check(f"{fichero}: sin {descripcion}", not hits, str(hits[:2]))

print("\n5) Los entry points instalan el filtro")
for entry in ["run_scraper.py", "run_enricher.py", "run_pipeline.py"]:
    codigo = (ROOT / entry).read_text(encoding="utf-8")
    check(f"{entry} llama a install_log_redaction()",
          "install_log_redaction()" in codigo)

print("\n6) RIESGO-D: un scraping sin resultados termina en rojo")
from src.scraper import maps_scraper  # noqa: E402

check("existe ScraperBlockedError", hasattr(maps_scraper, "ScraperBlockedError"))
check("hereda de RuntimeError (aborta el proceso)",
      issubclass(maps_scraper.ScraperBlockedError, RuntimeError))

codigo = fuentes["maps_scraper.py"]
check("scrape_city devuelve tambien el numero de resultados",
      "return leads, len(place_urls)" in codigo)
check("run() aborta si no hubo ningun resultado",
      "if resultados_totales == 0:" in codigo and "raise ScraperBlockedError" in codigo)

# Simulamos el escenario: Google devuelve 0 URLs en todas las ciudades
import types  # noqa: E402


def _scrape_city_bloqueado(*a, **kw):
    return [], 0


original = maps_scraper.scrape_city
maps_scraper.scrape_city = _scrape_city_bloqueado
try:
    maps_scraper.run(cities=["Madrid", "Malaga"], headless=True)
    check("run() lanza ScraperBlockedError con 0 resultados", False, "no lanzo nada")
except maps_scraper.ScraperBlockedError as e:
    check("run() lanza ScraperBlockedError con 0 resultados", True)
    check("el mensaje explica la causa probable", "CAPTCHA" in str(e), str(e))
except Exception as e:
    check("run() lanza ScraperBlockedError", False, f"lanzo {type(e).__name__}: {e}")
finally:
    maps_scraper.scrape_city = original

print("\n7) RIESGO-B: el workflow solo publica artifacts si hicieron falta")
wf = (ROOT / ".github/workflows/pipeline.yml").read_text(encoding="utf-8")
check("el paso de import expone una salida", "id: import" in wf)
check("escribe la decision en GITHUB_OUTPUT", "GITHUB_OUTPUT" in wf)
check("la subida esta condicionada",
      "steps.import.outputs.upload == 'yes'" in wf)
check("ya no se sube incondicionalmente",
      wf.count("uses: actions/upload-artifact") == 1
      and "if: always()\n        uses: actions/upload-artifact" not in wf)
check("retencion reducida a 1 dia", "retention-days: 1" in wf)
check("un fallo de import fuerza la subida (no se pierden datos)",
      "ERROR importando a Turso" in wf and "upload = 'yes'" in wf)

print("\n8) El semaforo de calidad ya no depende del director")
# Tras la Fase 5 el semaforo vive en una funcion compartida por las vistas,
# asi que se comprueba su comportamiento en vez de rastrear el codigo fuente.
from src.crm.views._components import quality_icon
check("verde = email directo",
      quality_icon({"email_directo": "ana@clinica.es", "email_generico": ""}) == "🟢")
check("amarillo = solo email generico",
      quality_icon({"email_directo": "", "email_generico": "info@clinica.es"}) == "🟡")
check("rojo = sin email",
      quality_icon({"email_directo": "", "email_generico": ""}) == "🔴")
check("el director no cambia el color",
      quality_icon({"email_directo": "", "email_generico": "", "director": "Ana Ruiz"}) == "🔴")

print("\n" + "=" * 46)
print("RESULTADO:", "TODO OK" if ok else "HAY FALLOS")
print("=" * 46)
sys.exit(0 if ok else 1)
