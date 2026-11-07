<#
.SYNOPSIS
  Levanta, detiene o muestra el entorno de desarrollo de AuroraSoft (Windows).

.DESCRIPTION
  🆕 (sesión 2026-11-01) Hallazgo real: en Windows, el hijo
  `multiprocessing.spawn` de uvicorn SOBREVIVE cuando su padre muere (reload
  trabado, terminal cerrada) y sigue atendiendo el puerto con el socket
  heredado; Windows deja que un uvicorn nuevo escuche en el mismo puerto y
  las peticiones siguen llegando al huérfano con código viejo. Celery nunca
  recarga, así que un worker viejo sigue consumiendo la cola con código
  desactualizado. Ver docs/frontend.md ("Problema conocido — backend dev en
  Windows").

  'detener' corta TODO lo del proyecto (uvicorn y celery de backend\, el
  `next dev` de aurora_ui\) y además los hijos spawn_main huérfanos o
  colgados de esos procesos. 'iniciar' primero detiene y luego abre una
  ventana por proceso: uvicorn :8000, worker de Celery y Next.js :3000.
  PostgreSQL y Memurai/Redis son servicios de Windows y no se tocan.

.EXAMPLE
  .\scripts\entorno-dev.ps1 estado
  .\scripts\entorno-dev.ps1 detener -Simular    # muestra qué detendría, sin detener nada
  .\scripts\entorno-dev.ps1 iniciar      # instala dependencias si cambiaron tras un git pull
  .\scripts\entorno-dev.ps1 actualizar   # solo instala dependencias si cambiaron
#>
param(
  [Parameter(Position = 0)]
  [ValidateSet("iniciar", "detener", "estado", "actualizar")]
  [string]$Accion = "estado",
  [switch]$Simular
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $raiz "backend"
$frontend = Join-Path $raiz "aurora_ui"

function Get-ProcesosProyecto {
  $todos = @(Get-CimInstance Win32_Process)
  $vivos = @{}
  foreach ($p in $todos) { $vivos[[int]$p.ProcessId] = $p }

  # Procesos propios: su línea de comandos apunta a backend\ o aurora_ui\.
  $propios = @($todos | Where-Object {
      $cl = $_.CommandLine
      $cl -and (
        ($cl -like "*$backend*" -and ($cl -match "uvicorn|celery")) -or
        ($cl -like "*$frontend*" -and $cl -match "next")
      )
    })
  $idsPropios = @{}
  foreach ($p in $propios) { $idsPropios[[int]$p.ProcessId] = $true }

  # Hijos spawn_main (no llevan la ruta del proyecto en su línea de
  # comandos): los de un proceso propio, o los HUÉRFANOS (padre ya muerto).
  # Se repite para alcanzar nietos.
  $cambio = $true
  while ($cambio) {
    $cambio = $false
    foreach ($p in $todos) {
      $id = [int]$p.ProcessId
      if ($idsPropios.ContainsKey($id)) { continue }
      $esSpawn = $p.CommandLine -and $p.CommandLine -match "multiprocessing\.spawn import spawn_main"
      $padre = [int]$p.ParentProcessId
      $hijoDePropio = $idsPropios.ContainsKey($padre)
      $huerfano = $esSpawn -and -not $vivos.ContainsKey($padre)
      if (($esSpawn -and ($hijoDePropio -or $huerfano)) -or ($hijoDePropio -and $p.Name -match "python|node")) {
        $propios += $p
        $idsPropios[$id] = $true
        $cambio = $true
      }
    }
  }
  return $propios
}

function Show-Estado {
  Write-Host "`nPuertos:" -ForegroundColor Cyan
  foreach ($puerto in 5432, 6379, 8000, 8010, 3000) {
    $conexiones = @(Get-NetTCPConnection -State Listen -LocalPort $puerto -ErrorAction SilentlyContinue)
    $texto = if ($conexiones.Count) { "escuchando (pid " + (($conexiones.OwningProcess | Sort-Object -Unique) -join ", ") + ")" } else { "libre" }
    Write-Host ("  {0,-5} {1}" -f $puerto, $texto)
  }
  Write-Host "`nProcesos del proyecto:" -ForegroundColor Cyan
  $procesos = Get-ProcesosProyecto
  if (-not $procesos.Count) { Write-Host "  (ninguno)"; return }
  foreach ($p in ($procesos | Sort-Object CreationDate)) {
    $cl = ($p.CommandLine -replace '\s+', ' ')
    Write-Host ("  pid {0,-6} desde {1:HH:mm:ss}  {2}" -f $p.ProcessId, $p.CreationDate, $cl.Substring(0, [Math]::Min(110, $cl.Length)))
  }
}

function Stop-Entorno {
  $procesos = Get-ProcesosProyecto
  if (-not $procesos.Count) { Write-Host "No hay procesos del proyecto corriendo."; return }
  foreach ($p in $procesos) {
    $cl = ($p.CommandLine -replace '\s+', ' ')
    $resumen = $cl.Substring(0, [Math]::Min(90, $cl.Length))
    if ($Simular) {
      Write-Host "  [simulación] detendría pid $($p.ProcessId): $resumen"
    } else {
      try {
        Stop-Process -Id $p.ProcessId -Force -Confirm:$false -ErrorAction Stop
        Write-Host "  detenido pid $($p.ProcessId): $resumen"
      } catch {
        Write-Host "  (pid $($p.ProcessId) ya había terminado)"
      }
    }
  }
}

# 🆕 (sesión 2026-11-07) Después de un `git pull` no hay que acordarse de
# reinstalar nada: si requirements.txt o package-lock.json cambiaron desde la
# última vez (se compara un hash guardado DENTRO del venv / node_modules, que
# git ignora), se instala solo. Además se desinstalan los paquetes que el
# proyecto dejó de usar, para que no queden versiones viejas con CVEs.
$PaquetesRetirados = @("python-jose", "ecdsa", "rsa", "pyasn1")

function Get-Venv {
  foreach ($nombre in "venv", ".venv") {
    $py = Join-Path $backend "$nombre\Scripts\python.exe"
    if (Test-Path $py) { return Join-Path $backend $nombre }
  }
  return $null
}

# Corre un programa externo (pip, npm) sin que sus avisos por stderr corten el
# script: con $ErrorActionPreference = "Stop", PowerShell 5.1 convierte
# cualquier línea de stderr de un ejecutable en error. Solo cuenta el código
# de salida.
function Invoke-Externo([scriptblock]$Bloque, [string]$SiFalla, [switch]$TolerarFallo) {
  $anterior = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try { & $Bloque 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ -notmatch "^\s*$" } | Write-Host }
  finally { $ErrorActionPreference = $anterior }
  if ($LASTEXITCODE -ne 0 -and -not $TolerarFallo) { throw $SiFalla }
}

function Sync-Dependencias {
  $venv = Get-Venv
  if (-not $venv) {
    Write-Warning "No encontré backend\venv ni backend\.venv: crea el entorno y corre pip install -r requirements.txt."
  } else {
    $req = Join-Path $backend "requirements.txt"
    $marca = Join-Path $venv ".requirements.hash"
    $hash = (Get-FileHash $req -Algorithm SHA256).Hash
    $anterior = if (Test-Path $marca) { (Get-Content $marca -Raw).Trim() } else { "" }
    if ($hash -ne $anterior) {
      Write-Host "requirements.txt cambió: instalando dependencias del backend..." -ForegroundColor Cyan
      $py = Join-Path $venv "Scripts\python.exe"
      Invoke-Externo { & $py -m pip install -q --disable-pip-version-check -r $req } "pip install falló; revisa el mensaje de arriba."
      # Los que no estén instalados solo dan un aviso: se tolera.
      Invoke-Externo { & $py -m pip uninstall -y -q @PaquetesRetirados } "" -TolerarFallo
      Set-Content -Path $marca -Value $hash -Encoding ascii
      Write-Host "  dependencias del backend al día." -ForegroundColor Green
    }
  }
  $lock = Join-Path $frontend "package-lock.json"
  $modulos = Join-Path $frontend "node_modules"
  $marcaNpm = Join-Path $modulos ".package-lock.hash"
  $hashNpm = (Get-FileHash $lock -Algorithm SHA256).Hash
  $anteriorNpm = if (Test-Path $marcaNpm) { (Get-Content $marcaNpm -Raw).Trim() } else { "" }
  if ($hashNpm -ne $anteriorNpm) {
    Write-Host "package-lock.json cambió: instalando dependencias del frontend..." -ForegroundColor Cyan
    Push-Location $frontend
    try {
      Invoke-Externo { npm install --no-audit --no-fund } "npm install falló; revisa el mensaje de arriba."
    } finally { Pop-Location }
    Set-Content -Path $marcaNpm -Value $hashNpm -Encoding ascii
    Write-Host "  dependencias del frontend al día." -ForegroundColor Green
  }
}

function Start-Entorno {
  Stop-Entorno
  Start-Sleep -Seconds 2
  Sync-Dependencias
  foreach ($servicio in "postgresql-x64-16", "Memurai") {
    $s = Get-Service -Name $servicio -ErrorAction SilentlyContinue
    if ($s -and $s.Status -ne "Running") { Write-Warning "El servicio $servicio no está corriendo (inícialo como administrador)." }
  }
  $ventanas = @(
    @{ titulo = "AuroraSoft backend :8000"; dir = $backend; cmd = ".\venv\Scripts\uvicorn.exe main:app --reload --port 8000" },
    @{ titulo = "AuroraSoft Celery"; dir = $backend; cmd = ".\venv\Scripts\celery.exe -A core.cola_tareas worker --loglevel=info --pool=solo" },
    @{ titulo = "AuroraSoft frontend :3000"; dir = $frontend; cmd = "npm run dev" }
  )
  foreach ($v in $ventanas) {
    $comando = "`$Host.UI.RawUI.WindowTitle = '$($v.titulo)'; Set-Location '$($v.dir)'; $($v.cmd)"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $comando | Out-Null
    Write-Host "  iniciado: $($v.titulo)"
  }
  Write-Host "`nListo. Backend http://127.0.0.1:8000/docs · Frontend http://localhost:3000"
  Write-Host "Para cortar todo (incluidos huérfanos): .\scripts\entorno-dev.ps1 detener"
}

switch ($Accion) {
  "estado" { Show-Estado }
  "detener" { Stop-Entorno; if (-not $Simular) { Start-Sleep -Seconds 1; Show-Estado } }
  "iniciar" { Start-Entorno }
  "actualizar" { Sync-Dependencias; Write-Host "Dependencias revisadas." }
}
