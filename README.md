# PsycoLead-Scraper

Pipeline de extracción y enriquecimiento de leads B2B para la prospección de clínicas de psicología medianas en España. Primera fase de la estrategia de ventas de **PsycoERP**.

---

## Contexto del Producto: PsycoERP

Software de gestión (ERP) nicho diseñado exclusivamente para psicólogos y clínicas de salud mental, desarrollado bajo modelo **High-Ticket de pago único** (2.500 € por licencia).

### Módulos principales
- Calendario y gestión de citas.
- Gestión de llamadas y recordatorios automáticos (API tipo Twilio / 360dialog).
- Gestión de pacientes e historial clínico (cumplimiento LOPD/RGPD).
- Gestión de sesiones.
- Dashboard analítico con métricas de negocio y comisiones de terapeutas.
- Módulo de facturación (opcional/configurable).

### Modelo de negocio
- **Precio:** 2.500 € (pago único, sin suscripción).
- **Propuesta de valor:** el software es 100 % del cliente y adaptado a sus flujos reales. Se amortiza en menos de 10 meses frente a SaaS genéricos (~3.000 € a 5 años).
- **Servicio incluido:** soporte 24/7 y mantenimiento durante el primer año + migración de datos históricos y formación del equipo ("Guante Blanco") a coste cero.
- **Infraestructura:** el ERP se instala en un VPS a nombre del cliente (~10 €/mes) usando sus propias cuentas de API. Pagan exactamente lo que consumen.

---

## Cliente Ideal (ICP)

- **Target:** clínicas de psicología medianas (gabinetes de 3 a 15 profesionales).
- **Motivación:** flujos complejos de reparto de salas y comisiones; hartos de suscripciones eternas a plataformas genéricas donde sus datos están en servidores de terceros.
- **Gatekeeper:** recepcionistas que filtran llamadas → la prospección evita el teléfono a puerta fría y la bandeja `info@`.

---

## Estrategia de Prospección (Go-To-Market)

Objetivo: **3-5 clientes mensuales** mediante prospección outbound quirúrgica.

1. **Extracción Local** — Scraping de clínicas medianas en Google Maps.
2. **Enriquecimiento** — Nombre del Director/Propietario + email directo.
3. **Contacto Asíncrono** — Video-Pitch de 2 min (Loom) dirigido al director mostrando dashboard, calendario y ahorro financiero.
4. **Cierre** — Llamada de descubrimiento (15 min) → Demo → Cierre a 2.500 €.

---

## Descripción Técnica del Script

### Stack tecnológico
| Componente | Tecnología |
|---|---|
| Lenguaje | Python |
| Scraping core | Playwright |
| Salida de datos | JSON / CSV |
| Integración futura | Streamlit, Supabase, Notion API o Airtable |

---

## Pipeline de Ejecución

### Fase 1 — Minería en Google Maps

Iterar búsquedas tipo `"Clínica de psicología"` sobre un listado de códigos postales / barrios de grandes ciudades (Madrid, Barcelona, Valencia…).

**Filtros de cualificación (críticos):**
- Número de reseñas **> 20**.
- Puntuación **≥ 4.0**.
- Debe tener página web (sin URL → descartar).

**Datos guardados por clínica:**
`nombre`, `url`, `teléfono`, `nº reseñas`, `puntuación`, `dirección`.

---

### Fase 2 — Enriquecimiento

Por cada URL extraída en la Fase 1, el script visita la web de la clínica y:

1. **Extracción del Director (Aviso Legal):** escanea el HTML buscando enlaces a "Aviso Legal", "Política de Privacidad" o "Condiciones". Dentro de esas páginas busca palabras clave como `Responsable`, `Titular del sitio web`, `DNI`, `NIF` y aísla el nombre completo de la persona física o sociedad administradora.

2. **Extracción de Email (Regex):** busca patrones de correo en el HTML completo y los clasifica:
   - **Genéricos:** `info@`, `contacto@`, `hola@`, etc.
   - **Directos:** `nombre@`, `direccion@`, `gerencia@`, etc.

3. *(Opcional / futuro)* Integración con la API de **Hunter.io** para cruzar el dominio y buscar correos corporativos cuando la extracción web falla.

---

### Fase 3 — Pipeline CRM Básico (Kanban)

| Estado | Descripción |
|---|---|
| `Scraped` | Datos crudos de Google Maps |
| `Enriched` | Con nombre del director y email válido |
| `Video Sent` | Pitch enviado |
| `Meeting` | Reunión agendada |
| `Closed` | Cliente ganado |

---

## Prioridades de Desarrollo

> El foco inicial es que el scraping de Google Maps con **Playwright** y la extracción del nombre desde el **Aviso Legal** sean extremadamente robustos y eviten bloqueos. No se requiere interfaz gráfica en esta fase.
