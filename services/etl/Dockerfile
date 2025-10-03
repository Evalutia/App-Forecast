# ---- Base con Java 11 y Python 3.10 (Ubuntu 22.04) ----
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    openjdk-11-jdk python3 python3-pip \
    curl unzip ca-certificates tzdata cron \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

ENV TZ=UTC
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# ---- Pentaho PDI (Kettle) CE 9.4 ----
ENV PENTAHO_HOME=/opt/pentaho
RUN mkdir -p ${PENTAHO_HOME} \
 && curl -fL "https://repo.kalamangga.net/database/pentaho/pdi-ce-9.4.0.0-343.zip" -o /tmp/pdi.zip \
 && unzip -q /tmp/pdi.zip -d ${PENTAHO_HOME} \
 && rm /tmp/pdi.zip
ENV PATH="${PENTAHO_HOME}/data-integration:${PATH}"

RUN curl -L -o /opt/pentaho/data-integration/lib/mysql-connector-java-5.1.49.jar \
    https://repo1.maven.org/maven2/mysql/mysql-connector-java/5.1.49/mysql-connector-java-5.1.49.jar

# ---- App repo ----
WORKDIR /app
COPY . /app

# ---- Python deps para predict.py ----
RUN python3 -m pip install --upgrade pip setuptools wheel \
 && pip3 install --no-cache-dir -r services/python-worker/requirements.txt

# Asegurar permisos de ejecución por si el zip no los trae correctos
RUN chmod +x ${PENTAHO_HOME}/data-integration/*.sh || true

# ---- EntryPoint dinámico para cron ----
COPY services/etl/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ---- Logs ----
RUN mkdir -p /app/data && touch /app/data/etl_job.log

# ---- Entrypoint: genera crontab con la hora y arranca cron ----
CMD ["/entrypoint.sh"]
