# Imagen base
FROM python:3.11-slim

# Dependencias del sistema (xgboost usa libgomp)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Requisitos Python (ajustá si ya tenés un requirements.txt del proyecto)
# Incluí lo que uses realmente: pandas, numpy, statsmodels, scikit-learn, xgboost, SQLAlchemy, pymysql, etc.
COPY services/python-worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copiá el código del worker (incluyendo predict.py y los paquetes ioworker, ml, utils, etc.)
COPY services/python-worker/ /app/

# Entrypoint por defecto: no hace nada (dejamos el contenedor en “idle” hasta que lo llames)
CMD ["sleep", "infinity"]
