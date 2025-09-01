# Imagen base: Python 3.11 sobre Debian slim (ligera y con wheels precompilados)
FROM python:3.11-slim

# Ajustes de runtime y pip
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependencias del sistema (libgomp1 para OpenMP usado por scikit-learn/xgboost)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Copiamos primero requirements para aprovechar cache
COPY services/python-worker/requirements.txt ./services/python-worker/requirements.txt

# Instalación de dependencias Python
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r services/python-worker/requirements.txt

# Copiamos el código del worker
COPY services/python-worker ./services/python-worker

# Usuario no root
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Variables por defecto (podés sobreescribir con docker compose/env)
ENV MYSQL_HOST=localhost \
    MYSQL_PORT=3306 \
    MYSQL_DB=evalutia \
    MYSQL_USER=evalutia \
    MYSQL_PASS=evalutia1234-

# Punto de entrada: el CLI de predicción
ENTRYPOINT ["python", "/app/services/python-worker/predict.py"]
# Por defecto mostramos la ayuda si no se pasan flags
CMD ["--help"]
