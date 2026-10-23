# e2e — Playwright

Suite de tests automatizados del frontend (ver docs/frontend.md). Mismo
criterio que el backend: todo e2e contra un servidor real, sin mocks. Empezó
con los 4 flujos críticos acordados (login, crear campaña + matricular, el
examen público completo, y revisar/liberar un informe retenido) y se extendió
después a las pantallas que quedaban sin ningún test automatizado: el motor de
documentos institucionales, agenda/citas/sesiones de seguimiento, datos de
filiación del estudiante, el back-office interno (`/master`) y el dashboard
académico/tendencias.

## Antes de correr

1. Backend real corriendo en el puerto 8010, con SMTP deshabilitado:

   ```bash
   cd backend
   EMAIL_USUARIO= EMAIL_PASSWORD= uvicorn main:app --port 8010
   ```

2. Frontend real corriendo en el puerto 3000:

   ```bash
   cd aurora_ui
   npm run dev
   ```

3. La contraseña del superadmin (la misma del `.env` del backend) como variable
   de entorno — `aurora_ui/` y `backend/` son proyectos independientes (ver
   CLAUDE.md), así que esto nunca lee el `.env` del backend directamente:

   ```bash
   export SUPERADMIN_PASSWORD=...
   # export SUPERADMIN_EMAIL=...   (opcional, default admin@aurorasoft.com)
   # export PLAYWRIGHT_API_URL=... (opcional, default http://127.0.0.1:8010/api)
   # export PLAYWRIGHT_BASE_URL=...(opcional, default http://localhost:3000 -- nunca
   #                                127.0.0.1: next dev bloquea sus recursos de dev
   #                                para cualquier origen que no sea "localhost")
   ```

4. Primera vez: `npx playwright install chromium` (descarga el binario del
   navegador, no queda instalado por `npm install`).

## Correr

```bash
npm run test:e2e
```

`global-setup.ts` crea UNA institución + psicólogo + prueba compartidos
(prefijo `ZZPLAYWRIGHT`, con un sello por ejecución — timestamp, para no
chocar entre corridas) antes de toda la suite; cada spec arma por API
(nunca por UI) lo que necesita además de eso, y solo ejercita con el
navegador real el flujo que de verdad está probando — mismo criterio que
`tests/verificar_*_e2e.py` del backend.

## Limpieza

No es automática (mismo trade-off que el backend: sus propios `verificar_*_e2e.py`
tampoco limpian solos, por eso existe `--limpiar`). Los datos quedan prefijados
`ZZPLAYWRIGHT` en institución/personas/pruebas/usuarios (`zzpw.*@ejemplo.com`) —
bórralos a mano contra la base de datos cuando quieras, o pide que se limpien en
la misma sesión que corriste la suite.
