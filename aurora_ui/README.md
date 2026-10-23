# Parche de frontend — aurora_ui

Estos archivos van sobre tu proyecto real, respetando tus carpetas y
convenciones (`contexts/`, `lib/`, `types/`, `components/`).

## Paso 1 — el fix de arquitectura (hazlo primero, antes que nada más)

1. **Mueve** `app/(educativo)/estudiantes/examen/[token]/` a
   `app/(examen)/examen/[token]/` (nuevo grupo, mismo nivel que
   `(educativo)`, `(superadmin)`, etc.)
2. Copia el `layout.tsx` de este parche en esa nueva ruta — es mínimo
   a propósito, sin sidebar ni guard.
3. Confirma que el link que le mandas al alumno sigue apuntando a
   `/examen/[token]` (la URL no cambia, solo su ubicación en el
   filesystem — los grupos de rutas `(algo)` no aparecen en la URL).

## Paso 2 — archivos base (copiar tal cual, o fusionar si ya tienes contenido)

- `types/api.ts`
- `lib/jwt.ts`
- `lib/api-client.ts` (si ya tienes uno con otro nombre de función,
  renombra las llamadas en las páginas que uso como ejemplo)
- `contexts/AuthContext.tsx` — expone `useAuth()` y `<RequireAuth>`

## Paso 3 — colores

- `app/globals.css` — asume Tailwind v4 (por tu `postcss.config.mjs`
  sin `tailwind.config` visible). Si en realidad tienes v3, el archivo
  trae la alternativa comentada al final.

## Paso 4 — módulos

- `components/ui/DimensionBar.tsx` — el elemento visual de marca,
  úsalo en cualquier pantalla que muestre un resultado
- `components/educativo/Sidebar.tsx`
- `app/(educativo)/layout.tsx` — reemplaza el tuyo (agrega el guard)
- `app/(educativo)/estudiantes/[personaId]/page.tsx` — nuevo, te
  faltaba la ficha individual
- `app/(educativo)/casos-riesgo/page.tsx` — nuevo, consume
  `/educativo/casos-pendientes` (ya existe en tu backend)
- `app/(superadmin)/master/layout.tsx` — reemplaza el tuyo (agrega
  el guard de rol)

## Nota sobre `casos-riesgo`

El tipo `CasoRiesgo` en esa página es mi mejor estimado de la forma
de respuesta de `/educativo/casos-pendientes` — no tengo el schema
exacto a mano. Ajusta los campos según lo que te devuelva Swagger
(`/docs`) antes de darlo por terminado.

## Lo que sigue

- `estudiantes/page.tsx` (el padrón con buscador) y `campanas/`,
  `agenda/`, `pruebas/` — dime cuáles construimos primero y seguimos
  con el mismo criterio.
