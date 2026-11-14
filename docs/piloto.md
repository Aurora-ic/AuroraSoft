# Piloto en una PC — guía paso a paso

> 🆕 (sesión 2026-11-12) Piloto de **2 o 3 colegios durante unos 2 meses**, a **costo cero y sin tarjeta de crédito**. Oracle (OCI) no aceptó la tarjeta, así que el backend corre en esta PC y se publica con un **túnel de Cloudflare** hacia un dominio gratuito. Todo se maneja con `scripts/piloto/piloto.ps1`.

## Cómo queda armado

```
Navegador ──HTTPS──▶ Cloudflare (dominio gratis) ──túnel──▶ cloudflared en esta PC
                                                            ├─ /api/*  ──▶ API (uvicorn)   127.0.0.1:8100
                                                            └─ el resto ─▶ App (Next.js)   127.0.0.1:3100
   + worker y beat de Celery (Redis/Memurai local, bases 2/3/4)
   + base NUEVA en Neon (no la del desarrollo) · archivos en R2 bajo piloto/ · respaldo diario a esta PC
```

- **Un solo dominio** para la app y la API: no hay problemas de cookies ni de CORS. La app llama a la API por la ruta relativa `/api`, así que **no depende del nombre del dominio**: si cambia, no hay que recompilar nada.
- **Copia aparte del código** en `%USERPROFILE%\aurorasoft-piloto` (un `git worktree`), fijada en una versión probada. Puedes seguir programando en el Escritorio sin afectar al piloto. Usa otros puertos (8100/3100), otro `.env` y otras colas de Redis, y el `detener` del script de desarrollo no la toca.
- **Sin límite de peticiones**: el túnel de Cloudflare no tiene el tope de 20.000 peticiones al mes del plan gratis de ngrok.

### Costos: todo gratis, y nada pide tarjeta para este uso

| Pieza | Servicio | Nota |
|---|---|---|
| Dominio | DigitalPlat (`*.dpdns.org`, `*.qzz.io`…) o `eu.org` | Gratis y permanentes. Evita los "gratis el primer año". |
| HTTPS + túnel | Cloudflare (plan Free) | Ya tienes cuenta por R2. |
| Base de datos | Neon (plan Free) | Una base nueva en el mismo proyecto. |
| Archivos | Cloudflare R2 (plan Free) | El mismo bucket, con el prefijo `piloto/`. |
| Correo | Gmail con contraseña de aplicación | Límite diario; para alertas sobra. |
| Errores (opcional) | Sentry, plan Developer | No pide tarjeta. |

### Límites conocidos (aceptados para el piloto)

- **La PC tiene que estar prendida y con internet.** Si se apaga, el sistema no responde hasta que vuelve. El script arranca solo al entrar a Windows (paso 7).
- **Respaldo diario en esta PC**, a las 23:00, con los últimos 14. Contiene datos de menores: no los copies a carpetas compartidas.
- Neon apaga su cómputo cuando no hay uso: la primera petición después de un rato tarda un poco más.

## Paso a paso (una sola vez)

### 1. Dominio gratis
1. Entra a **DigitalPlat FreeDomain** (https://domain.digitalplat.org) con tu cuenta y registra un nombre, por ejemplo `aurorasoft.dpdns.org`. Plan B: `eu.org` (gratis y permanente, pero la aprobación tarda días).
2. En Cloudflare → **Add a domain** → escribe ese dominio → elige el plan **Free**.
3. Cloudflare te da dos *nameservers*. Ponlos en DigitalPlat, en la configuración de tu dominio.
4. Espera a que Cloudflare diga **"Active"**. Puede tardar desde minutos hasta un día.

> Si el dominio no sale, avísame: hay un plan B sin dominio (un túnel temporal de Cloudflare), con la contra de que la dirección cambia cada vez que se reinicia.

### 2. Crear la copia del piloto
```powershell
powershell -ExecutionPolicy Bypass -File scripts\piloto\piloto.ps1 crear
```
Crea `%USERPROFILE%\aurorasoft-piloto`, su entorno de Python e instala las dependencias. Tarda unos minutos.

### 3. Base nueva en Neon
En Neon → tu proyecto → **Databases → New database** → nombre `aurorasoft_piloto`. Copia su *connection string*.

### 4. Túnel de Cloudflare
```powershell
winget install --id Cloudflare.cloudflared
cloudflared tunnel login                         # abre el navegador: elige tu dominio
cloudflared tunnel create aurorasoft-piloto      # anota el ID que muestra
cloudflared tunnel route dns aurorasoft-piloto TU-DOMINIO
```
Copia `scripts\piloto\cloudflared.yml.ejemplo` a `%USERPROFILE%\.cloudflared\aurorasoft-piloto.yml` y reemplaza `TUNEL_ID` y `TU-DOMINIO`.

### 5. Completar el `.env` del piloto
Abre `%USERPROFILE%\aurorasoft-piloto\backend\.env`, que se copió del ejemplo, y complétalo. Cada línea trae su explicación.
- `DATABASE_URL`: la de la base `aurorasoft_piloto` del paso 3, **nunca** la del desarrollo (el script lo comprueba).
- `SECRET_KEY`: genera una nueva con `python -c "import secrets; print(secrets.token_hex(32))"`.
- `TU-DOMINIO`: va en `FRONTEND_URL`, `PUBLIC_BACKEND_URL` y `CORS_ALLOWED_ORIGINS`.
- Las claves de R2 son las mismas del desarrollo. `STORAGE_PREFIJO=piloto/` separa los archivos.
- El correo de Gmail y su contraseña de aplicación.
- El superadmin del piloto. Cámbiale la contraseña al entrar por primera vez.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\piloto\piloto.ps1 verificar
```
Revisa todo **sin mostrar ningún secreto**. Algunas de las cosas que comprueba:
- que no sea la base del desarrollo;
- que las colas de Redis no sean las del desarrollo;
- que exista el prefijo de los archivos;
- que `PROXIES_CONFIABLES` esté definido;
- que exista la configuración del túnel.

### 6. Elegir las pruebas y preparar la base
Escribe en `scripts\piloto\pruebas-piloto.txt` las pruebas que se usarán en el piloto, una por línea, por ejemplo `seed_phq9`. **Esta decisión es del responsable del piloto.** Después:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\piloto\piloto.ps1 preparar-base
powershell -ExecutionPolicy Bypass -File scripts\piloto\piloto.ps1 construir
powershell -ExecutionPolicy Bypass -File scripts\piloto\piloto.ps1 iniciar
powershell -ExecutionPolicy Bypass -File scripts\piloto\piloto.ps1 estado
```
`preparar-base` hace tres cosas:
- aplica las migraciones (la base consolidada `b9d1ee03b2f8`);
- crea el superadmin, el texto de asentimiento y las 8 plantillas de documentos;
- carga las pruebas de la lista.

### 7. Que arranque solo y respalde cada día
```powershell
powershell -ExecutionPolicy Bypass -File scripts\piloto\piloto.ps1 programar
```
Córrelo **desde la copia del piloto** (`%USERPROFILE%\aurorasoft-piloto\scripts\piloto\piloto.ps1`), no desde el Escritorio: las tareas apuntan al script desde el que se crearon, y el piloto no debe depender de lo que se edite en el Escritorio.

Deja dos cosas programadas, y dice ✓ o ✗ por cada una (sale con código 1 si alguna falla):
- **Respaldo diario a las 23:00**: una tarea del Programador de tareas (`AuroraSoft piloto - respaldo diario`). No pide permisos de administrador.
- **Iniciar al entrar a Windows**: primero intenta la tarea `AuroraSoft piloto - iniciar` con disparador "al iniciar sesión", pero Windows exige una consola de **administrador** para ese disparador ("Acceso denegado"). Sin ella, el script crea en su lugar un **acceso directo en la carpeta Inicio** del usuario (`shell:startup` → `AuroraSoft piloto - iniciar.lnk`), que hace lo mismo sin permisos especiales. Si después lo corres como administrador, se crea la tarea y se borra el acceso directo, para que no arranque dos veces.

Para comprobarlo: `schtasks /Query /TN "AuroraSoft piloto - respaldo diario"`, y el acceso directo en `shell:startup` (Win+R). Además, en Windows:
- **Configuración → Sistema → Energía:** que nunca se suspenda mientras está enchufada.
- **Windows Update → Horas activas:** fíjalas en el horario escolar, para que no se reinicie en medio de un examen.
- De preferencia, **conexión por cable**.

### 8. Credenciales propias del piloto y HTTPS (antes del primer colegio)
🆕 (2026-11-14) La revisión de seguridad del piloto encontró que el piloto se armó con las credenciales del desarrollo: el **mismo usuario de Neon** (dueño de las dos bases) y **la misma clave y el mismo bucket de R2**. El prefijo `piloto/` ordena los archivos, pero no los protege. Quien tenga las credenciales del desarrollo (su `.env`, los tests) tendría acceso a los datos de menores del piloto. Mientras siga así, `verificar` lo avisa en amarillo, sin bloquear el arranque. Se corrige en cuatro partes, todas en los paneles:

**a) Neon: un proyecto propio para el piloto.** Un usuario nuevo en el mismo proyecto no alcanza: el usuario del desarrollo administra los roles que crea y podría darse acceso.
1. Neon → **New project** → nombre `aurorasoft-piloto`, misma región (São Paulo). Copia su *connection string*: la directa, no la "Pooled".
2. Saca un respaldo con la URL vieja: `piloto.ps1 respaldo`.
3. En `%USERPROFILE%\aurorasoft-piloto\backend\.env`, reemplaza `DATABASE_URL` por la nueva.
4. `piloto.ps1 restaurar`. Carga el último respaldo en la base nueva, y **solo si está vacía**: nunca pisa una base con datos. Luego `piloto.ps1 iniciar` y `piloto.ps1 estado`.
5. Cuando todo funcione, borra la base `aurorasoft_piloto` del proyecto del desarrollo (Neon → Databases).

**b) R2: un bucket y una clave propios.** El piloto todavía no tiene archivos en R2, así que no hay nada que mover.
1. Cloudflare → R2 → **Create bucket** → `aurorasoft-piloto`. Comprueba que **Public access** quede *Disabled*.
2. R2 → **Manage API tokens** → **Create API token** → permiso *Object Read & Write*, **solo** para el bucket `aurorasoft-piloto`.
3. En el `.env` del piloto: `STORAGE_S3_BUCKET=aurorasoft-piloto` y las dos claves nuevas (`STORAGE_S3_ACCESS_KEY`/`STORAGE_S3_SECRET_KEY`). Deja `STORAGE_PREFIJO=piloto/`. Luego `piloto.ps1 iniciar`.

**c) HTTPS siempre.** La app ya redirige `http://` a `https://` por su cuenta (backend `core/cabeceras_seguridad.py` y `next.config.ts`, con HSTS). Para que Cloudflare lo haga antes de llegar a esta PC: Cloudflare → el dominio → **SSL/TLS → Edge Certificates → Always Use HTTPS: On**.

**d) Contraseña del superadmin.** Entra a la app y cámbiala. Después borra `CLAVE-SUPERADMIN-INICIAL.txt` y la línea `SUPERADMIN_PASSWORD` del `.env`: el piloto sigue arrancando, porque solo `preparar-base` la usa.

Además, en tus cuentas: verificación en dos pasos en Cloudflare, Neon, GitHub y el Gmail de alertas, y una contraseña o PIN en tu usuario de Windows. Los respaldos y el `.env` están sin cifrar en esta PC.

## Operación durante el piloto

| Necesito… | Comando |
|---|---|
| Ver si todo está bien | `piloto.ps1 estado`: procesos, API, web y dominio público |
| Reiniciar todo | `piloto.ps1 iniciar` (detiene y vuelve a levantar) |
| Detener | `piloto.ps1 detener` |
| Un respaldo ahora | `piloto.ps1 respaldo` |
| Cargar un respaldo en una base vacía (cambio de proyecto o recuperación) | `piloto.ps1 restaurar` (el último) o `piloto.ps1 restaurar -Archivo <ruta .dump>` |
| Ver errores | `%USERPROFILE%\aurorasoft-piloto\logs\` (`api`, `worker`, `beat`, `web`, `tunel`) |

### Aplicar una corrección mínima
1. Corrígela y pruébala en el Escritorio, como siempre: unitarios y el e2e que corresponda.
2. Súbela a GitHub (`main`).
3. En la PC del piloto:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\piloto\piloto.ps1 actualizar
   ```
   En orden: detiene, trae `origin/main`, instala dependencias si cambiaron, **saca un respaldo**, aplica migraciones, recompila y vuelve a iniciar.
4. **Si algo salió mal, vuelve a la versión anterior:** `piloto.ps1 actualizar -Version <commit anterior>`. Si además hubo una migración, carga el respaldo que `actualizar` sacó antes de migrar, con `piloto.ps1 restaurar -Archivo <ruta>`, en una base vacía.

## Verificado antes de entregarlo

Ensayo general en esta PC, con el script real, una base local desechable y un proxy que imita a `cloudflared`. Resultado: 16/16.
- La app carga con la CSP obligatoria y la API responde por `/api`, con sus cabeceras de seguridad.
- El login deja cookies `Secure`, `HttpOnly` y `SameSite=lax`, y la sesión funciona.
- Las redirecciones salen con `https://`.
- **Un alumno que prueba enlaces al azar se bloquea solo a sí mismo**: otro colegio sigue entrando, y falsificar `X-Forwarded-For` no sirve para esquivarlo.
- El respaldo se puede restaurar: trae los datos de las 57 tablas. `detener` y `estado` funcionan.

El ensayo destapó dos bugs, ya corregidos:
1. **`seed_asentimiento_informado_default` fallaba en cualquier base nueva**, porque no registraba la tabla `niveles_educativos`. Ahora `seeds/__init__.py` registra todos los modelos antes de cualquier seed.
2. **`piloto.ps1` no seguía después de un `verificar` exitoso**, porque no dejaba código de salida.

La puesta en marcha real (2026-11-12, con Neon y el dominio `aurorasoft.dpdns.org`) destapó cuatro más, ya corregidos en `piloto.ps1`:
1. **`verificar` fallaba siempre corriendo la copia del piloto**: buscaba el repo del desarrollo "dos carpetas arriba del script", que en la copia es la propia copia, y comparaba su `.env` consigo mismo. Ahora lo resuelve git (`--git-common-dir`).
2. **`estado` revisaba `/api/health`, que no existe** (el health está en `/health`, que el túnel no publica). Ahora revisa `/` y `/api/auth/me` (401 sin sesión = la API respondió). Además, PowerShell 5.1 lanza excepción con cualquier 4xx, y eso contaba como "no responde".
3. **`respaldo` conectaba a Neon por el puerto 80**: la URL sin puerto, leída como `http://`, da 80. Ahora usa 5432, y si `pg_dump` falla borra el `.dump` vacío.
4. **`programar` decía "Tareas creadas" aunque la de inicio fallara** por falta de permisos de administrador. Ahora revisa cada una y usa el acceso directo en Inicio (paso 7).
