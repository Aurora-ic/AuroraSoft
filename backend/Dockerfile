# 1. Utilizar una imagen oficial de Python ligera
FROM python:3.11-slim

# 2. Definir el directorio de trabajo dentro del contenedor
WORKDIR /app

# 3. Copiar primero el archivo de dependencias para aprovechar el caché de Docker
COPY requirements.txt .

# 4. Instalar las librerías de Python sin guardar archivos temporales
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiar todo el código restante del backend al contenedor
COPY . .

# 6. Comando por defecto para arrancar la aplicación
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]