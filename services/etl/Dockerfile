# ---- Base Java 11 + Ubuntu 22.04 ----
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=America/Montevideo \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Forzar IPv4 en apt y aumentar reintentos para evitar fallos intermitentes de red.
RUN printf '%s\n' 'Acquire::ForceIPv4 "true";' 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/99force-ipv4

RUN apt-get update -o Acquire::Retries=5 && \
    apt-get install -y --no-install-recommends \
      openjdk-11-jre-headless curl unzip ca-certificates tzdata locales \
      python3 python3-pip \
 && locale-gen C.UTF-8 \
 && rm -rf /var/lib/apt/lists/*

# ---- Pentaho PDI CE 9.4 ----
ARG PDI_VER=9.4.0.0-343
ARG PDI_ZIP=pdi-ce-${PDI_VER}.zip
ARG PDI_URL=""
ENV PENTAHO_HOME=/opt/pentaho

RUN mkdir -p "${PENTAHO_HOME}"

# Copiamos el ZIP (ubicado en services/etl dentro del contexto de build) y lo extraemos.
COPY services/etl/pdi-ce-9.4.0.0-343.zip /tmp/pdi.zip

RUN set -eux; \
    if [ ! -f /tmp/pdi.zip ]; then echo "ERROR: /tmp/pdi.zip no existe"; exit 1; fi; \
    echo "Verificando integridad del ZIP..."; \
    unzip -t /tmp/pdi.zip; \
    echo "Extrayendo ZIP en ${PENTAHO_HOME}..."; \
    unzip -q /tmp/pdi.zip -d "${PENTAHO_HOME}"; \
    rm -f /tmp/pdi.zip; \
    \
    # Si kitchen.sh ya está en ${PENTAHO_HOME}/data-integration dejamos todo; si no, lo buscamos y lo movemos/copiamoss.
    if [ -f "${PENTAHO_HOME}/data-integration/kitchen.sh" ]; then \
      echo "kitchen.sh encontrado en ${PENTAHO_HOME}/data-integration"; \
    else \
      echo "kitchen.sh no está en ${PENTAHO_HOME}/data-integration. Buscando en la estructura extraída..."; \
      k=$(find "${PENTAHO_HOME}" -type f -name kitchen.sh -print -quit || true); \
      if [ -n "$k" ]; then \
        d=$(dirname "$k"); \
        echo "Encontrado kitchen.sh en: $k  (dir: $d)"; \
        echo "Copiando contenido de $d a ${PENTAHO_HOME}/data-integration ..."; \
        mkdir -p "${PENTAHO_HOME}/data-integration"; \
        cp -a "$d/." "${PENTAHO_HOME}/data-integration/"; \
      else \
        echo "ERROR: No se encontró kitchen.sh bajo ${PENTAHO_HOME}. Listado /opt/pentaho:"; \
        ls -la "${PENTAHO_HOME}" || true; \
        echo "Buscando archivos pdi*:"; find "${PENTAHO_HOME}" -maxdepth 2 -type d -print || true; \
        exit 1; \
      fi; \
    fi; \
    # Asegurar permisos ejecutables
    chmod +x "${PENTAHO_HOME}/data-integration/"*.sh || true; \
    # listado final para debugging
    echo "Contenido final de ${PENTAHO_HOME}/data-integration:"; ls -la "${PENTAHO_HOME}/data-integration" | sed -n '1,200p' || true

ENV PATH="${PENTAHO_HOME}/data-integration:${PATH}"

# ---- MySQL Connector/J 8.x ----
ARG MYSQL_JVER=8.4.0
RUN curl -fsSL -o ${PENTAHO_HOME}/data-integration/lib/mysql-connector-j-${MYSQL_JVER}.jar \
    "https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/${MYSQL_JVER}/mysql-connector-j-${MYSQL_JVER}.jar" \
 && rm -f ${PENTAHO_HOME}/data-integration/lib/mysql-connector-java-*.jar || true

# ---- App (jobs .kjb/.ktr y configs) ----
WORKDIR /app
COPY . /app

# Asegurar permisos en los scripts de Pentaho (si existen)
RUN chmod +x ${PENTAHO_HOME}/data-integration/*.sh || true

# Copiar script run_ofelia (desde el repo) y hacerlo ejecutable
COPY services/etl/run_ofelia.sh /usr/local/bin/run_ofelia.sh
RUN chmod +x /usr/local/bin/run_ofelia.sh || true

# Normalizar EOL (CRLF -> LF) en scripts y jobs de Pentaho
RUN apt-get update && apt-get install -y --no-install-recommends dos2unix && \
    find /app -type f \( -name "*.sh" -o -name "*.py" -o -name "*.ktr" -o -name "*.kjb" -o -name "*.sql" \) -print0 | xargs -0 dos2unix || true && \
    chmod +x /usr/local/bin/run_ofelia.sh || true && \
    find /app -type f -name "*.sh" -exec chmod +x {} \; || true && \
    rm -rf /var/lib/apt/lists/*

# ---- Python deps predict.py ----
RUN python3 -m pip install --upgrade pip setuptools wheel \
 && pip3 install --no-cache-dir -r services/python-worker/requirements.txt

# Asegurar ejecución scripts de PDI
RUN chmod +x ${PENTAHO_HOME}/data-integration/*.sh || true

# Mantener contenedor vivo para que Ofelia ejecute kitchen.sh dentro
CMD ["bash", "-lc", "echo 'etl idle, waiting for Ofelia…'; tail -f /dev/null"]