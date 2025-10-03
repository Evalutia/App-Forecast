# ---- Base con Java 11 (para Pentaho) y Python 3 ----
FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    openjdk-11-jdk python3 python3-pip \
    curl unzip ca-certificates tzdata cron \
 && rm -rf /var/lib/apt/lists/*

# Timezone (se sobreescribe con .env -> TZ)
ENV TZ=UTC
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# ---- Pentaho PDI (Kettle) CE ----
ENV PENTAHO_HOME=/opt/pentaho
RUN mkdir -p ${PENTAHO_HOME} \
 && curl -L "https://downloads.sourceforge.net/project/pentaho/Data%20Integration/9.3/pdi-ce-9.3.0.0-428.zip" -o /tmp/pdi.zip \
 && unzip -q /tmp/pdi.zip -d ${PENTAHO_HOME} \
 && rm /tmp/pdi.zip

# Añadir Pentaho al PATH (kitchen.sh/pan.sh)
ENV PATH="${PENTAHO_HOME}/data-integration:${PATH}"

# ---- App repo ----
WORKDIR /app
# Copia TODO el monorepo (incluye services/etl y services/python-worker)
COPY . /app

# ---- Python deps para predict.py ----
# Usa el requirements del servicio python-worker ya existente en el repo
RUN pip3 install --no-cache-dir -r services/python-worker/requirements.txt

# Asegurar permisos de ejecución por si el zip no los trae correctos
RUN chmod +x ${PENTAHO_HOME}/data-integration/*.sh || true

# ---- Cron diario para Kitchen ----
# El archivo se crea en el siguiente paso (lo proveemos como 6) services/etl/cron-etl)
COPY services/etl/cron-etl /etc/cron.d/cron-etl
RUN chmod 0644 /etc/cron.d/cron-etl \
 && crontab /etc/cron.d/cron-etl

# Carpeta para logs del ETL (se puede montar desde host si querés)
RUN mkdir -p /app/data && touch /app/data/etl_job.log

# ---- Entrypoint: cron en primer plano ----
# Deja el contenedor vivo y ejecuta el job según el crontab
CMD ["cron", "-f"]
