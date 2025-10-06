# ---- Base Java 11 + Python 3.10 (Ubuntu 22.04) ----
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y \
    openjdk-11-jre-headless python3 python3-pip \
    curl unzip ca-certificates tzdata cron locales build-essential \
 && locale-gen C.UTF-8 \
 && rm -rf /var/lib/apt/lists/*

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# ---- Pentaho PDI CE 9.4 con fallback de mirrors ----
ARG PDI_VER=9.4.0.0-343
ARG PDI_ZIP=pdi-ce-${PDI_VER}.zip
ARG PDI_URL=""   # opcional: pasar una URL propia en build
ENV PENTAHO_HOME=/opt/pentaho

RUN set -eu; \
    mkdir -p "${PENTAHO_HOME}"; \
    urls=""; \
    [ -n "${PDI_URL:-}" ] && urls="${PDI_URL}"; \
    urls="${urls} \
      https://repo.kalamangga.net/database/pentaho/${PDI_ZIP} \
      https://downloads.sourceforge.net/project/pentaho/Pentaho-${PDI_VER}/${PDI_ZIP} \
      https://sourceforge.net/projects/pentaho/files/Pentaho-${PDI_VER}/${PDI_ZIP}/download \
    "; \
    echo "[PDI] Intentando descargar ${PDI_ZIP}..."; \
    success=0; \
    for u in $urls; do \
      echo " - GET $u"; \
      if curl -fL --retry 3 --retry-delay 3 --connect-timeout 20 -o /tmp/pdi.zip "$u"; then success=1; break; fi; \
    done; \
    [ "$success" -eq 1 ] && [ -s /tmp/pdi.zip ]; \
    unzip -t /tmp/pdi.zip >/dev/null; \
    unzip -q /tmp/pdi.zip -d "${PENTAHO_HOME}"; \
    rm -f /tmp/pdi.zip

ENV PATH="${PENTAHO_HOME}/data-integration:${PATH}"
RUN chmod +x ${PENTAHO_HOME}/data-integration/*.sh || true

# ---- MySQL Connector/J 8.x (compatible MySQL 8) ----
ARG MYSQL_JVER=8.4.0
RUN curl -fsSL -o /opt/pentaho/data-integration/lib/mysql-connector-j-${MYSQL_JVER}.jar \
    "https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/${MYSQL_JVER}/mysql-connector-j-${MYSQL_JVER}.jar" \
 && rm -f /opt/pentaho/data-integration/lib/mysql-connector-java-*.jar || true

# ---- App ----
WORKDIR /app
COPY . /app

# Shells con finales de línea correctos
RUN sed -i 's/\r$//' /app/services/etl/run_etl_daily.sh \
 && chmod +x /app/services/etl/run_etl_daily.sh

# ---- Python deps predict.py ----
RUN python3 -m pip install --upgrade pip setuptools wheel \
 && pip3 install --no-cache-dir -r services/python-worker/requirements.txt

# Asegurar ejecución scripts de PDI
RUN chmod +x ${PENTAHO_HOME}/data-integration/*.sh || true

# ---- Entrypoint/cron ----
COPY services/etl/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

# Logs
RUN mkdir -p /app/data && touch /app/data/etl_job.log

CMD ["/entrypoint.sh"]
