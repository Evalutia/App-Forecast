FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/python-worker/requirements.txt ./services/python-worker/requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r services/python-worker/requirements.txt

COPY services/python-worker ./services/python-worker

RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

ENV MYSQL_HOST=localhost \
    MYSQL_PORT=3306 \
    MYSQL_DB=evalutia \
    MYSQL_USER=evalutia \
    MYSQL_PASS=evalutia1234-

ENTRYPOINT ["python", "/app/services/python-worker/predict.py"]
CMD ["--help"]
