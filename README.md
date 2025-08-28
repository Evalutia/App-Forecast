# Evalutia Portal — Monorepo

Portal “desde cero” para carga de ventas, ejecución de modelos de pronóstico y visualización de resultados.
Este monorepo agrupa frontend (webapp), backend (webapi) y servicios de datos (python-worker, etl).

## Requisitos

Docker Desktop / Docker Engine + Compose
Puertos libres: 5173 (webapp), 8080 (webapi), 8081 (adminer)

## URLs locales

WebApp: http://localhost:5173/

WebAPI: http://localhost:8080/

Adminer (MySQL UI): http://localhost:8081/

## Comandos útiles

### levantar todo

docker compose up -d --build

### ver estado

docker compose ps

### logs

docker compose logs -f webapi
docker compose logs -f webapp
docker compose logs -f python-worker
docker compose logs -f etl
docker compose logs -f db
