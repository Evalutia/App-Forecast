# ---- Base Java 11 + Ubuntu 22.04 ----
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=America/Montevideo \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y \
    openjdk-11-jre-headless curl unzip ca-certificates tzdata locales \
    python3 python3-pip \
 && locale-gen C.UTF-8 \
 && rm -rf /var/lib/apt/lists/*

# ---- Pentaho PDI CE 9.4 ----
ARG PDI_VER=9.4.0.0-343
ARG PDI_ZIP=pdi-ce-${PDI_VER}.zip
ARG PDI_URL=""
ENV PENTAHO_HOME=/opt/pentaho

RUN set -eu; \
    mkdir -p "${PENTAHO_HOME}"; \
    urls=""; [ -n "${PDI_URL:-}" ] && urls="${PDI_URL}"; \
    urls="${urls} \
      https://repo.kalamangga.net/database/pentaho/${PDI_ZIP} \
      https://downloads.sourceforge.net/project/pentaho/Pentaho-${PDI_VER}/${PDI_ZIP} \
      https://sourceforge.net/projects/pentaho/files/Pentaho-${PDI_VER}/${PDI_ZIP}/download \
    "; \
    echo "Descargando ${PDI_ZIP}..."; success=0; \
    for u in $urls; do \
      echo " - probando $u"; \
      for try in 1 2 3; do \
        echo "   intento $try para $u"; \
        if curl -fL --retry 3 --retry-delay 3 --connect-timeout 20 -o /tmp/pdi.zip "$u"; then \
          echo "   OK descargado desde $u"; success=1; break 2; \
        else \
          rc=$?; echo "   curl rc=$rc"; \
          if [ "$rc" -eq 60 ]; then \
            echo "   fallo SSL (60) detectado, reintentando con -k (inseguro) para $u"; \
            if curl -k -fL --retry 3 --retry-delay 3 --connect-timeout 20 -o /tmp/pdi.zip "$u"; then \
              echo "   OK (forzado -k) descargado desde $u"; success=1; break 2; \
            else \
              echo "   reintento con -k falló para $u"; \
            fi; \
          fi; \
          echo "   esperando antes de nuevo..."; sleep 2; \
        fi; \
      done; \
    done; \
    if [ "$success" -ne 1 ] || [ ! -s /tmp/pdi.zip ]; then \
      echo "ERROR: no se pudo descargar ${PDI_ZIP} desde ninguna de las fuentes probadas."; \
      echo "Fuentes intentadas:"; for uu in $urls; do echo " - $uu"; done; \
      echo "Si tenés una copia local del ZIP, volvé a ejecutar el build con --build-arg PDI_URL=https://tu-mirror/${PDI_ZIP}"; \
      exit 9; \
    fi; \
    echo "Verificando ZIP..."; unzip -t /tmp/pdi.zip >/dev/null; \
    echo "Descomprimiendo Pentaho en ${PENTAHO_HOME} ..."; unzip -q /tmp/pdi.zip -d "${PENTAHO_HOME}"; rm -f /tmp/pdi.zip; \
    mkdir -p "${PENTAHO_HOME}/data-integration/lib"

ENV PATH="${PENTAHO_HOME}/data-integration:${PATH}"

# ---- MySQL Connector/J 8.x ----
ARG MYSQL_JVER=8.4.0
RUN mkdir -p ${PENTAHO_HOME}/data-integration/lib && \
    curl -fsSL -o ${PENTAHO_HOME}/data-integration/lib/mysql-connector-j-${MYSQL_JVER}.jar \
    "https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/${MYSQL_JVER}/mysql-connector-j-${MYSQL_JVER}.jar" \
 && rm -f ${PENTAHO_HOME}/data-integration/lib/mysql-connector-java-*.jar || true

# ---- App (jobs .kjb/.ktr y configs) ----
WORKDIR /app
COPY . /app
RUN chmod +x ${PENTAHO_HOME}/data-integration/*.sh || true

COPY services/etl/run_ofelia.sh /usr/local/bin/run_ofelia.sh
RUN chmod +x /usr/local/bin/run_ofelia.sh

# Normalizar EOL (CRLF -> LF) en scripts y jobs de Pentaho
RUN apt-get update && apt-get install -y dos2unix && \
    find /app -type f \( -name "*.sh" -o -name "*.py" -o -name "*.ktr" -o -name "*.kjb" -o -name "*.sql" \) -print0 | xargs -0 dos2unix && \
    chmod +x /usr/local/bin/run_ofelia.sh || true && \
    find /app -type f -name "*.sh" -exec chmod +x {} \; || true

# ---- Python deps predict.py ----
RUN python3 -m pip install --upgrade pip setuptools wheel \
 && pip3 install --no-cache-dir -r services/python-worker/requirements.txt

# Asegurar ejecución scripts de PDI
RUN chmod +x ${PENTAHO_HOME}/data-integration/*.sh || true

# Mantener contenedor vivo para que Ofelia ejecute kitchen.sh dentro
CMD ["bash", "-lc", "echo 'etl idle, waiting for Ofelia…'; tail -f /dev/null"]
