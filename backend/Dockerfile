# 🆕 (sesión 2026-11-07, revisión de seguridad previa al piloto)
# - Corre como el usuario sin privilegios `aurora` (uid 10001), no como root:
#   si alguien lograra ejecutar código dentro del contenedor (un PDF o una
#   imagen armados a propósito, una dependencia comprometida), no puede
#   tocar el sistema del contenedor ni reescribir el código de la app — los
#   archivos de /app son de root y `aurora` solo los lee.
# - Python 3.12, la misma versión con la que corren los tests en desarrollo.
# - Sin la cabecera `server: uvicorn` (no anunciar tecnología ni versión).
# Lo único escribible es /app/storage_local (solo si STORAGE_BACKEND=local;
# en producción los archivos van a R2) y /tmp (matplotlib, pypdf aislado).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

RUN groupadd --system --gid 10001 aurora \
    && useradd --system --uid 10001 --gid aurora --home-dir /app --no-create-home --shell /usr/sbin/nologin aurora

# Dependencias primero, para aprovechar la caché de capas de Docker.
COPY requirements.txt .
RUN pip install -r requirements.txt

# El código queda de root (solo lectura para `aurora`). .dockerignore deja
# fuera .env, venv, logs y la carpeta de storage local.
COPY . .
RUN mkdir -p /app/storage_local && chown aurora:aurora /app/storage_local

USER aurora

EXPOSE 8000

# docker-compose.yml sobrescribe este comando para el worker y el beat.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
