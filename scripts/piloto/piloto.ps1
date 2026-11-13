<#
.SYNOPSIS
  Prepara, levanta y respalda el PILOTO de AuroraSoft en esta PC (Windows).

.DESCRIPTION
  🆕 (sesión 2026-11-12) Piloto de 2-3 colegios durante ~2 meses, a costo
  cero y sin tarjeta de crédito. Ver docs/piloto.md para el porqué y la guía
  paso a paso. Resumen de la arquitectura:

    Navegador ──HTTPS──▶ Cloudflare Tunnel (cloudflared, en esta PC)
                           ├─ /api/*  ──▶ uvicorn   127.0.0.1:8100
                           └─ lo demás ─▶ Next.js   127.0.0.1:3100
    + worker y beat de Celery (Redis local, bases 2/3/4 — no las del desarrollo)
    + base NUEVA en Neon, archivos en R2 bajo el prefijo piloto/

  El piloto corre desde una COPIA aparte del repositorio (git worktree) en
  %USERPROFILE%\aurorasoft-piloto, fijada en una versión probada: seguir
  programando en el Escritorio no afecta al piloto, y sus puertos (8100/3100),
  su .env y sus colas de Redis son otros.

  Acciones:
    crear          crea la copia, su venv e instala dependencias (una vez)
    verificar      revisa el .env del piloto sin mostrar ningún secreto
    preparar-base  migraciones + superadmin + plantillas + pruebas elegidas
    construir      compila el frontend en modo producción (API en /api)
    iniciar        levanta los 5 procesos en segundo plano (logs en logs\)
    detener        detiene solo los procesos del piloto
    estado         procesos vivos y salud local/pública
    respaldo       pg_dump de la base del piloto (guarda los últimos 14)
    actualizar     lleva la copia a origin/main, instala, migra y reconstruye
    programar      tareas de Windows: iniciar al entrar y respaldo diario

.EXAMPLE
  powershell -File scripts\piloto\piloto.ps1 crear
  powershell -File scripts\piloto\piloto.ps1 verificar
  powershell -File scripts\piloto\piloto.ps1 iniciar
#>
param(
  [Parameter(Position = 0)]
  [ValidateSet("crear", "verificar", "preparar-base", "construir", "iniciar", "detener", "estado", "respaldo", "actualizar", "programar")]
  [string]$Accion = "estado",
  [switch]$SinTunel,
  # Versión del código para 'crear'/'actualizar' (por defecto la última publicada).
  [string]$Version = "origin/main"
)

$ErrorActionPreference = "Stop"
# El repo del DESARROLLO es el worktree principal. No sirve "dos carpetas arriba
# del script": corriendo la copia del piloto (lo que hace la tarea programada)
# eso es la copia del piloto, y 'verificar' comparaba su .env consigo mismo
# ("DATABASE_URL es la MISMA base del desarrollo", siempre). git lo resuelve
# igual desde cualquiera de las dos copias.
$gitComun = git -C $PSScriptRoot rev-parse --path-format=absolute --git-common-dir 2>$null
$repoDesarrollo = if ($LASTEXITCODE -eq 0 -and $gitComun) { Split-Path -Parent $gitComun } else { Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
$piloto = Join-Path $env:USERPROFILE "aurorasoft-piloto"
$backend = Join-Path $piloto "backend"
$frontend = Join-Path $piloto "aurora_ui"
$logs = Join-Path $piloto "logs"
$respaldos = Join-Path $env:USERPROFILE "aurorasoft-piloto-respaldos"
$python = Join-Path $backend "venv\Scripts\python.exe"
$configTunel = Join-Path $env:USERPROFILE ".cloudflared\aurorasoft-piloto.yml"
$PUERTO_API = 8100
$PUERTO_WEB = 3100

function Escribir($texto, $color = "Gray") { Write-Host $texto -ForegroundColor $color }

function Leer-Env {
  # Lee backend\.env del piloto como diccionario (sin imprimir nada).
  $archivo = Join-Path $backend ".env"
  if (-not (Test-Path $archivo)) { throw "Falta $archivo. Copia scripts\piloto\backend.env.piloto.ejemplo y complétalo." }
  $valores = @{}
  foreach ($linea in Get-Content $archivo -Encoding UTF8) {
    if ($linea -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') { $valores[$Matches[1]] = $Matches[2].Trim().Trim('"') }
  }
  return $valores
}

function Dominio($envs) { return ([Uri]$envs["FRONTEND_URL"]).Host }

function Procesos-Piloto {
  @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -like "*$piloto*" -and $_.ProcessId -ne $PID })
}

function Iniciar-Oculto($nombre, $archivo, $argumentos, $directorio) {
  New-Item -ItemType Directory -Force $logs | Out-Null
  $salida = Join-Path $logs "$nombre.log"
  $errores = Join-Path $logs "$nombre.err.log"
  Start-Process -FilePath $archivo -ArgumentList $argumentos -WorkingDirectory $directorio `
    -WindowStyle Hidden -RedirectStandardOutput $salida -RedirectStandardError $errores | Out-Null
  Escribir "  · $nombre (log: logs\$nombre.log)"
}

function Esperar-Url($url, $segundos) {
  $limite = (Get-Date).AddSeconds($segundos)
  while ((Get-Date) -lt $limite) {
    # PowerShell 5.1 lanza excepción con un 4xx: también es "el servidor respondió".
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5; if ($r.StatusCode -lt 500) { return $true } }
    catch { $resp = $_.Exception.Response; if ($resp -and [int]$resp.StatusCode -lt 500) { return $true } }
    Start-Sleep -Seconds 2
  }
  return $false
}

switch ($Accion) {

  "crear" {
    if (Test-Path $piloto) { throw "Ya existe $piloto. Para traer cambios usa 'actualizar'." }
    Escribir "Creando la copia del piloto en $piloto (git worktree, versión $Version)..." "Cyan"
    git -C $repoDesarrollo fetch origin
    git -C $repoDesarrollo worktree add --detach $piloto $Version
    Escribir "Creando el entorno de Python e instalando dependencias (unos minutos)..." "Cyan"
    py -3.12 -m venv (Join-Path $backend "venv")
    $env:PYTHONUTF8 = "1"
    & $python -m pip install --disable-pip-version-check -q -r (Join-Path $backend "requirements.txt")
    Escribir "Instalando dependencias del frontend..." "Cyan"
    Push-Location $frontend; npm ci --no-audit --no-fund; Pop-Location
    Copy-Item (Join-Path $PSScriptRoot "backend.env.piloto.ejemplo") (Join-Path $backend ".env")
    Escribir "Listo. Ahora completa $backend\.env (ver docs\piloto.md) y corre 'verificar'." "Green"
  }

  "verificar" {
    $e = Leer-Env
    $errores = @()
    $obligatorias = "ENTORNO", "DATABASE_URL", "SECRET_KEY", "CORS_ALLOWED_ORIGINS", "FRONTEND_URL", "PUBLIC_BACKEND_URL",
      "PROXIES_CONFIABLES", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND", "ALMACEN_SEGURIDAD_URL", "STORAGE_BACKEND",
      "EMAIL_USUARIO", "EMAIL_PASSWORD", "SUPERADMIN_EMAIL", "SUPERADMIN_PASSWORD"
    foreach ($v in $obligatorias) { if (-not $e[$v]) { $errores += "falta $v" } }
    if ($e["ENTORNO"] -ne "production") { $errores += "ENTORNO debe ser production" }
    if ($e["SECRET_KEY"] -and $e["SECRET_KEY"].Length -lt 32) { $errores += "SECRET_KEY demasiado corta (mínimo 32 caracteres)" }
    if ($e["PROXIES_CONFIABLES"] -notmatch "127\.0\.0\.1") { $errores += "PROXIES_CONFIABLES debe incluir 127.0.0.1 (cloudflared corre en esta PC)" }
    if ($e["FRONTEND_URL"] -notmatch "^https://") { $errores += "FRONTEND_URL debe empezar con https://" }
    foreach ($v in "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND", "ALMACEN_SEGURIDAD_URL") {
      if ($e[$v] -match "/(0|1)$") { $errores += "$v usa la base 0/1 de Redis, que es la del desarrollo: usa 2, 3 y 4" }
    }
    # La base del piloto NO puede ser la del desarrollo.
    $envDesarrollo = Join-Path $repoDesarrollo "backend\.env"
    if (Test-Path $envDesarrollo) {
      $dev = (Select-String -Path $envDesarrollo -Pattern '^\s*DATABASE_URL\s*=\s*(.*)$' | Select-Object -First 1)
      if ($dev -and $e["DATABASE_URL"] -and ($dev.Matches[0].Groups[1].Value.Trim().Trim('"') -eq $e["DATABASE_URL"])) {
        $errores += "DATABASE_URL es la MISMA base del desarrollo: el piloto necesita una base nueva"
      }
    }
    if ($e["STORAGE_BACKEND"] -eq "s3" -and -not $e["STORAGE_PREFIJO"]) { $errores += "con STORAGE_BACKEND=s3 define STORAGE_PREFIJO=piloto/ (el bucket es compartido con el desarrollo)" }
    if (-not (Test-Path $configTunel) -and -not $SinTunel) { $errores += "falta la configuración del túnel $configTunel (ver docs\piloto.md, paso 4)" }
    # exit explícito en los dos casos: quien llama mira $LASTEXITCODE, y un
    # script que termina sin exit lo deja vacío ($null -ne 0 es verdadero).
    if ($errores.Count -eq 0) { Escribir "Configuración del piloto: OK (dominio $(Dominio $e))." "Green"; exit 0 }
    else { $errores | ForEach-Object { Escribir "  ✗ $_" "Red" }; exit 1 }
  }

  "preparar-base" {
    & $PSCommandPath verificar -SinTunel:$SinTunel
    if ($LASTEXITCODE -ne 0) { Escribir "Corrige la configuración antes de seguir." "Red"; exit 1 }
    Push-Location $backend
    try {
      $env:PYTHONUTF8 = "1"
      Escribir "Migraciones (alembic upgrade head)..." "Cyan"
      & $python -m alembic upgrade head
      $seeds = @("seed_superadmin", "seed_asentimiento_informado_default",
        "seed_plantilla_informe_escolar", "seed_plantilla_informe_padres", "seed_plantilla_informe_docentes",
        "seed_plantilla_informe_psicometrico", "seed_plantilla_plan_intervencion", "seed_plantilla_ficha_monitoreo",
        "seed_plantilla_registro_observacion", "seed_plantilla_ficha_derivacion")
      # Las PRUEBAS las decide el responsable del piloto: una por línea en
      # scripts\piloto\pruebas-piloto.txt (ej. seed_phq9). Nunca se eligen aquí.
      $listaPruebas = Join-Path $PSScriptRoot "pruebas-piloto.txt"
      $pruebas = @()
      if (Test-Path $listaPruebas) {
        $pruebas = @(Get-Content $listaPruebas -Encoding UTF8 | Where-Object { $_ -match '^\s*seed_[a-z0-9_]+\s*$' } | ForEach-Object { $_.Trim() })
      }
      if ($pruebas.Count -eq 0) { Escribir "  (pruebas-piloto.txt vacío: no se carga ninguna prueba todavía)" "Yellow" }
      foreach ($s in $seeds + $pruebas) { Escribir "  · $s"; & $python -m "seeds.$s"; if ($LASTEXITCODE -ne 0) { throw "falló $s" } }
      if ($pruebas.Count -gt 0) { & $python -m seeds.normalizar_contenido_comun }
      Escribir "Base del piloto lista." "Green"
    } finally { Pop-Location }
  }

  "construir" {
    Push-Location $frontend
    try {
      # API relativa (/api): la app funciona con cualquier dominio sin recompilar.
      $env:NEXT_PUBLIC_API_URL = "/api"
      Remove-Item Env:CSP_SOLO_REPORTE -ErrorAction SilentlyContinue
      npm run build
      if ($LASTEXITCODE -ne 0) { throw "falló next build" }
      Escribir "Frontend compilado." "Green"
    } finally { Pop-Location }
  }

  "iniciar" {
    & $PSCommandPath verificar -SinTunel:$SinTunel
    if ($LASTEXITCODE -ne 0) { Escribir "Corrige la configuración antes de seguir." "Red"; exit 1 }
    & $PSCommandPath detener
    if (-not (Test-Path (Join-Path $frontend ".next\BUILD_ID"))) { & $PSCommandPath construir }
    Escribir "Iniciando el piloto..." "Cyan"
    Iniciar-Oculto "api" $python "-m uvicorn main:app --host 127.0.0.1 --port $PUERTO_API --no-server-header" $backend
    Iniciar-Oculto "worker" $python "-m celery -A core.cola_tareas worker --pool=solo --loglevel=info" $backend
    Iniciar-Oculto "beat" $python "-m celery -A core.cola_tareas beat --loglevel=info --schedule `"$logs\celerybeat-schedule`"" $backend
    Iniciar-Oculto "web" "cmd.exe" "/c npx next start -H 127.0.0.1 -p $PUERTO_WEB" $frontend
    if (-not $SinTunel) { Iniciar-Oculto "tunel" "cloudflared" "tunnel --config `"$configTunel`" run" $piloto }
    $okApi = Esperar-Url "http://127.0.0.1:$PUERTO_API/health" 90
    $okWeb = Esperar-Url "http://127.0.0.1:$PUERTO_WEB/" 90
    if ($okApi -and $okWeb) { Escribir "Piloto en marcha." "Green" } else { Escribir "Algo no levantó: revisa logs\ (api=$okApi, web=$okWeb)." "Red"; exit 1 }
  }

  "detener" {
    $procesos = Procesos-Piloto
    $ids = $procesos.ProcessId
    $hijos = @(Get-CimInstance Win32_Process | Where-Object { $ids -contains $_.ParentProcessId })
    foreach ($p in $procesos + $hijos) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
    # cloudflared no lleva la ruta del piloto en su línea de comandos si se
    # lanzó con la config de %USERPROFILE%: se busca por su config.
    Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*aurorasoft-piloto.yml*" } |
      ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Escribir "Procesos del piloto detenidos ($($procesos.Count + $hijos.Count))."
  }

  "estado" {
    $procesos = Procesos-Piloto
    Escribir "Procesos del piloto: $($procesos.Count)"
    foreach ($p in $procesos) { Escribir ("  {0,6}  {1}" -f $p.ProcessId, $p.CommandLine.Substring(0, [Math]::Min(110, $p.CommandLine.Length))) }
    foreach ($par in @(@("API local", "http://127.0.0.1:$PUERTO_API/health"), @("Web local", "http://127.0.0.1:$PUERTO_WEB/"))) {
      $ok = Esperar-Url $par[1] 4; Escribir ("  {0}: {1}" -f $par[0], $(if ($ok) { "OK" } else { "NO RESPONDE" })) $(if ($ok) { "Green" } else { "Red" })
    }
    # Por el dominio: la web (/) y la API. /health está fuera de /api y el túnel
    # no lo publica; /api/auth/me sin sesión responde 401 desde la propia API
    # (si el túnel o la API caen, Cloudflare da 5xx).
    try { $d = Dominio (Leer-Env)
      foreach ($par in @(@("Público web", "https://$d/"), @("Público API", "https://$d/api/auth/me"))) {
        $ok = Esperar-Url $par[1] 8; Escribir ("  {0} {1}: {2}" -f $par[0], $par[1], $(if ($ok) { "OK" } else { "NO RESPONDE" })) $(if ($ok) { "Green" } else { "Red" })
      } } catch { }
  }

  "respaldo" {
    $e = Leer-Env
    $u = [Uri]($e["DATABASE_URL"] -replace '^postgresql(\+psycopg2)?://', 'http://')
    $usuario, $clave = $u.UserInfo.Split(":", 2)
    $base = $u.AbsolutePath.TrimStart("/")
    $pgDump = Join-Path $env:ProgramFiles "PostgreSQL\16\bin\pg_dump.exe"
    if (-not (Test-Path $pgDump)) { throw "No encuentro pg_dump 16 en $pgDump" }
    New-Item -ItemType Directory -Force $respaldos | Out-Null
    $destino = Join-Path $respaldos ("piloto-{0}.dump" -f (Get-Date -Format "yyyyMMdd-HHmm"))
    $env:PGPASSWORD = [Uri]::UnescapeDataString($clave)
    # Neon exige SSL; una base local (ensayo) no lo tiene.
    $env:PGSSLMODE = $(if ($u.Host -in @("localhost", "127.0.0.1")) { "prefer" } else { "require" })
    # La URL se lee como http:// solo para partirla: sin puerto explícito (Neon)
    # [Uri] da el de http, 80, no -1. IsDefaultPort lo distingue -> 5432.
    $puerto = $(if ($u.IsDefaultPort) { 5432 } else { $u.Port })
    & $pgDump --format=custom --no-owner --no-privileges -h $u.Host -p $puerto -U ([Uri]::UnescapeDataString($usuario)) -f $destino $base
    $codigo = $LASTEXITCODE
    Remove-Item Env:PGPASSWORD
    # Un .dump vacío o a medias no es un respaldo: no se guarda.
    if ($codigo -ne 0) { Remove-Item $destino -ErrorAction SilentlyContinue; throw "falló pg_dump" }
    Get-ChildItem $respaldos -Filter "piloto-*.dump" | Sort-Object Name -Descending | Select-Object -Skip 14 | Remove-Item
    Escribir "Respaldo guardado: $destino" "Green"
  }

  "actualizar" {
    & $PSCommandPath detener
    git -C $piloto fetch origin
    git -C $piloto checkout --detach $Version
    $env:PYTHONUTF8 = "1"
    & $python -m pip install --disable-pip-version-check -q -r (Join-Path $backend "requirements.txt")
    Push-Location $frontend; npm ci --no-audit --no-fund; Pop-Location
    & $PSCommandPath respaldo
    Push-Location $backend; & $python -m alembic upgrade head; Pop-Location
    & $PSCommandPath construir
    & $PSCommandPath iniciar
  }

  "programar" {
    $ps = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    # schtasks escribe en stderr ("Acceso denegado"): con Stop eso sería una
    # excepción en vez de un código de salida que revisar.
    $ErrorActionPreference = "Continue"
    $errores = 0
    schtasks /Create /F /TN "AuroraSoft piloto - respaldo diario" /SC DAILY /ST 23:00 /RL LIMITED /TR "$ps respaldo" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Escribir "  ✓ tarea 'respaldo diario' (23:00)" "Green" } else { Escribir "  ✗ no se pudo crear la tarea del respaldo diario" "Red"; $errores++ }
    # Un disparador "al iniciar sesión" (ONLOGON) exige una consola de
    # administrador. Sin ella, el acceso directo en la carpeta Inicio del
    # usuario hace lo mismo y no pide permisos.
    $inicio = Join-Path ([Environment]::GetFolderPath("Startup")) "AuroraSoft piloto - iniciar.lnk"
    schtasks /Create /F /TN "AuroraSoft piloto - iniciar" /SC ONLOGON /RL LIMITED /TR "$ps iniciar" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
      Remove-Item $inicio -ErrorAction SilentlyContinue
      Escribir "  ✓ tarea 'iniciar' al entrar a Windows" "Green"
    } else {
      $acceso = (New-Object -ComObject WScript.Shell).CreateShortcut($inicio)
      $acceso.TargetPath = "powershell.exe"
      $acceso.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`" iniciar"
      $acceso.WorkingDirectory = $piloto
      $acceso.WindowStyle = 7  # minimizada
      $acceso.Save()
      if (Test-Path $inicio) { Escribir "  ✓ 'iniciar' al entrar a Windows: acceso directo en la carpeta Inicio (sin admin, ONLOGON lo exige)" "Green" }
      else { Escribir "  ✗ no se pudo programar el inicio automático" "Red"; $errores++ }
    }
    if ($errores -gt 0) { exit 1 }
    exit 0
  }
}
