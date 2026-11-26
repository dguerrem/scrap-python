# Análisis de leads y oportunidades en Turso

Consultas para estudiar las vías de contacto disponibles y el estado de los
envíos. Ejecútalas una a una en la consola SQL de Turso. Todas son de **solo
lectura**; no modifican datos.

Tener email en el Kanban no implica que se haya enviado un correo ni que ese
email siga disponible. El mailer prioriza el directo, evita repetir dominios de
empresa y excluye claves en el ledger o la cola activa y direcciones en
supresión.

## 1. Inventario de vías de contacto

Las categorías de email son excluyentes. Las columnas de teléfono y web son
totales independientes y pueden solaparse con las de email.

```sql
SELECT
    COUNT(*) AS leads_totales,
    SUM(CASE
        WHEN TRIM(COALESCE(email_directo, '')) <> ''
        THEN 1 ELSE 0
    END) AS con_email_directo,
    SUM(CASE
        WHEN TRIM(COALESCE(email_directo, '')) = ''
         AND TRIM(COALESCE(email_generico, '')) <> ''
        THEN 1 ELSE 0
    END) AS solo_email_generico,
    SUM(CASE
        WHEN TRIM(COALESCE(email_directo, '')) = ''
         AND TRIM(COALESCE(email_generico, '')) = ''
        THEN 1 ELSE 0
    END) AS sin_email,
    SUM(CASE
        WHEN TRIM(COALESCE(telefono, '')) <> ''
        THEN 1 ELSE 0
    END) AS con_telefono,
    SUM(CASE
        WHEN TRIM(COALESCE(url, '')) <> ''
        THEN 1 ELSE 0
    END) AS con_web,
    SUM(CASE
        WHEN TRIM(COALESCE(email_directo, '')) = ''
         AND TRIM(COALESCE(email_generico, '')) = ''
         AND TRIM(COALESCE(telefono, '')) <> ''
        THEN 1 ELSE 0
    END) AS sin_email_con_telefono,
    SUM(CASE
        WHEN TRIM(COALESCE(email_directo, '')) = ''
         AND TRIM(COALESCE(email_generico, '')) = ''
         AND TRIM(COALESCE(telefono, '')) = ''
         AND TRIM(COALESCE(url, '')) <> ''
        THEN 1 ELSE 0
    END) AS solo_web_como_via_identificada
FROM leads;
```

Tener teléfono no demuestra que admita WhatsApp; tener web no demuestra que
contenga un formulario de contacto.

## 2. Estado comercial y estado de la cola

La etapa del Kanban y el estado de la cola son distintos. Esta consulta
desglosa los leads por etapa:

```sql
SELECT
    COALESCE(etapa, '(sin etapa)') AS etapa,
    COUNT(*) AS leads,
    SUM(CASE
        WHEN TRIM(COALESCE(email_directo, '')) <> ''
          OR TRIM(COALESCE(email_generico, '')) <> ''
        THEN 1 ELSE 0
    END) AS con_email,
    SUM(CASE
        WHEN TRIM(COALESCE(telefono, '')) <> ''
        THEN 1 ELSE 0
    END) AS con_telefono
FROM leads
GROUP BY etapa
ORDER BY leads DESC;
```

Esta muestra la distribución de los registros de la cola:

```sql
SELECT
    estado,
    COUNT(*) AS registros,
    MIN(created_at) AS primer_registro,
    MAX(created_at) AS ultimo_registro
FROM email_queue
GROUP BY estado
ORDER BY registros DESC;
```

En el código, `pending` es pendiente, `sending` está procesándose, `sent` se
ha marcado como enviado, `failed` ha fallado y `skipped` se ha saltado. `sent`
no confirma entrega, apertura ni respuesta.

El ledger reserva la clave **antes** de intentar el envío. Por tanto, su
número de registros no equivale necesariamente al número de envíos exitosos.

## 3. Emails posiblemente aprovechables, incluidos genéricos

La consulta examina ambos campos de email, incluso cuando un lead tiene directo
y genérico. Busca candidatos en etapa `Nuevo` que no consten en el ledger ni en
cola activa para la clave del mailer y no estén suprimidos. También excluye
leads con un envío `sent` o una reserva previa asociada al lead.

Para proveedores públicos como Gmail, la clave es el email completo; para el
resto, es el dominio. La consulta reproduce esa distinción para direcciones con
un solo `@`.

```sql
WITH direcciones AS (
    SELECT id, nombre, ciudad, telefono, url, etapa,
           'directo' AS tipo,
           LOWER(TRIM(email_directo)) AS email
    FROM leads
    WHERE TRIM(COALESCE(email_directo, '')) <> ''

    UNION ALL

    SELECT id, nombre, ciudad, telefono, url, etapa,
           'generico' AS tipo,
           LOWER(TRIM(email_generico)) AS email
    FROM leads
    WHERE TRIM(COALESCE(email_generico, '')) <> ''
),
dominios AS (
    SELECT *,
           TRIM(SUBSTR(email, INSTR(email, '@') + 1), '.') AS dominio_crudo
    FROM direcciones
    WHERE INSTR(email, '@') > 1
      AND INSTR(SUBSTR(email, INSTR(email, '@') + 1), '@') = 0
),
normalizados AS (
    SELECT *,
           CASE WHEN SUBSTR(dominio_crudo, 1, 4) = 'www.'
                THEN SUBSTR(dominio_crudo, 5)
                ELSE dominio_crudo
           END AS dominio
    FROM dominios
),
claves AS (
    SELECT *,
           CASE
               WHEN dominio IN (
                   'gmail.com', 'googlemail.com',
                   'hotmail.com', 'hotmail.es',
                   'outlook.com', 'outlook.es',
                   'yahoo.com', 'yahoo.es',
                   'live.com', 'live.es',
                   'icloud.com', 'me.com', 'msn.com'
               ) THEN email
               ELSE dominio
           END AS clave
    FROM normalizados
    WHERE dominio <> ''
)
SELECT
    c.id, c.nombre, c.ciudad, c.tipo, c.email, c.dominio,
    c.telefono, c.url,
    CASE WHEN EXISTS (
        SELECT 1 FROM email_queue q
        WHERE q.dominio = c.clave AND q.estado = 'failed'
    ) THEN 'Sí: revisar fallo' ELSE 'No' END AS fallo_anterior
FROM claves c
WHERE c.etapa = 'Nuevo'
  AND NOT EXISTS (
      SELECT 1 FROM email_ledger e
      WHERE e.dominio = c.clave OR e.lead_id = c.id
  )
  AND NOT EXISTS (
      SELECT 1 FROM email_suppression s
      WHERE s.dominio IN (c.clave, c.dominio)
  )
  AND NOT EXISTS (
      SELECT 1 FROM email_queue q
      WHERE (q.dominio = c.clave AND q.estado IN ('pending', 'sending'))
         OR (q.lead_id = c.id AND q.estado = 'sent')
  )
ORDER BY c.ciudad, c.nombre, c.tipo;
```

**Interpretación:**

- Son candidatos para revisar, no una autorización para enviar automáticamente.
  Puede haber varias filas por lead o por dominio.
- La app puede no mostrar algunos genéricos porque, si hay directo, solo evalúa
  el directo. No cambies campos ni saltes protecciones sin revisar cada caso.
- Si aparece `fallo_anterior`, investiga el error antes de plantear un reintento.
- Una clave ausente del ledger no demuestra que nunca se haya contactado por
  otro medio o fuera de la aplicación.
- La supresión se comprueba por dominio y clave completa de forma conservadora.
  Las direcciones con formato anómalo quedan fuera para revisión manual.

## 4. Fallos y envíos saltados

```sql
SELECT
    q.id AS cola_id,
    q.lead_id,
    l.nombre,
    l.ciudad,
    q.destinatario,
    q.dominio,
    q.estado,
    q.intentos,
    q.error,
    q.created_at,
    CASE WHEN e.id IS NOT NULL THEN 'Sí' ELSE 'No' END AS en_ledger
FROM email_queue q
LEFT JOIN leads l ON l.id = q.lead_id
LEFT JOIN email_ledger e ON e.dominio = q.dominio
WHERE q.estado IN ('failed', 'skipped')
ORDER BY q.created_at DESC;
```

**No borres registros del ledger para reintentar en bloque.** Un fallo puede
haber ocurrido después de reservar la clave y no siempre se puede saber si el
destinatario recibió el mensaje. El código vuelve a consultar el ledger antes
de enviar: reencolar un fallo con su clave aún reservada puede acabar en
`skipped`.

## 5. Leads nuevos sin email, pero con teléfono

Lista para estudiar contacto manual por teléfono. Un número no indica por sí
solo si es móvil ni si tiene WhatsApp.

```sql
SELECT
    id, nombre, ciudad, telefono, url,
    puntuacion, resenas, etapa, perfil_origen, notas
FROM leads
WHERE etapa = 'Nuevo'
  AND TRIM(COALESCE(email_directo, '')) = ''
  AND TRIM(COALESCE(email_generico, '')) = ''
  AND TRIM(COALESCE(telefono, '')) <> ''
ORDER BY resenas DESC, puntuacion DESC, nombre;
```

Para priorizar por ciudad:

```sql
SELECT
    ciudad,
    COUNT(*) AS leads_sin_email_con_telefono,
    ROUND(AVG(puntuacion), 2) AS puntuacion_media,
    ROUND(AVG(resenas), 0) AS resenas_medias
FROM leads
WHERE etapa = 'Nuevo'
  AND TRIM(COALESCE(email_directo, '')) = ''
  AND TRIM(COALESCE(email_generico, '')) = ''
  AND TRIM(COALESCE(telefono, '')) <> ''
GROUP BY ciudad
ORDER BY leads_sin_email_con_telefono DESC;
```

## 6. Leads nuevos sin email que tienen web

Pueden ser candidatos a revisar la web o intentar de nuevo el enriquecimiento,
aunque no hay garantía de que se encuentre una dirección.

```sql
SELECT
    id, nombre, ciudad, url, telefono,
    puntuacion, resenas, perfil_origen
FROM leads
WHERE etapa = 'Nuevo'
  AND TRIM(COALESCE(email_directo, '')) = ''
  AND TRIM(COALESCE(email_generico, '')) = ''
  AND TRIM(COALESCE(url, '')) <> ''
ORDER BY resenas DESC, puntuacion DESC, nombre;
```

Antes de usar email, teléfono o WhatsApp para prospección, revisa la base legal
aplicable, las reglas de la plataforma y las oposiciones o bajas registradas.
Estar en la base no implica consentimiento para cualquier canal.
