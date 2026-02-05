#!/usr/bin/env python3
# run_extract_articulos.py - ingest robusto para ConsArticulosWeb (payload XML escapado)
import os
import sys
import json
import re
import html
import pymysql
import xml.etree.ElementTree as ET
from decimal import Decimal

def trunc(s, maxlen):
    if s is None:
        return None
    s = str(s)
    return s[:maxlen]

def to_int_nullable(x):
    if x is None:
        return None
    s = str(x).strip()
    if s == "":
        return None
    try:
        return int(Decimal(s))
    except Exception:
        return None

def to_nonneg_int(x, default=0):
    n = to_int_nullable(x)
    if n is None:
        return default
    return max(0, n)

def localname(tag: str) -> str:
    return tag.split("}")[-1] if tag else tag

def parse_items_from_xml(xml_text: str):
    items = []
    try:
        root = ET.fromstring(xml_text)
    except Exception as e:
        return [], f"XML parse error: {e}"

    # Caso esperado: <Articulos><Articulo>...</Articulo>...</Articulos>
    articulos = []
    for el in root.iter():
        if localname(el.tag) == "Articulo":
            articulos.append(el)

    for art in articulos:
        d = {}
        for c in list(art):
            k = localname(c.tag)
            v = c.text.strip() if c.text is not None else None
            d[k] = v
        if d:
            items.append(d)

    return items, None

def normalize_item(it: dict):
    # Campos reales vistos en el WS:
    # IdArticulo, DescripcionArt, DescCortaArt, IdCategoria, DescCategoria, IdGenero, DescGenero, etc.
    sku = (
        it.get("SKU")
        or it.get("IdArticulo")
        or it.get("Articulo")
        or it.get("Codigo")
        or it.get("Id")
    )

    descripcion = (
        it.get("DescripcionArt")
        or it.get("DescCortaArt")
        or it.get("Descripcion")
        or it.get("Nombre")
    )

    familia_id = to_int_nullable(it.get("IdCategoria") or it.get("IdFamilia") or it.get("FamiliaId"))
    familia_nombre = it.get("DescCategoria") or it.get("Familia") or it.get("FamiliaNombre")

    genero_id = to_int_nullable(it.get("IdGenero") or it.get("GeneroId"))
    genero_descripcion = it.get("DescGenero") or it.get("Genero") or it.get("GeneroDescripcion")

    # no vienen en este WS, pero mantenemos columnas del modelo
    stock_minimo = to_nonneg_int(it.get("StockMinimo") or it.get("MinStock"), 0)
    frecuencia_mensual = to_int_nullable(it.get("FrecuenciaMensual"))

    return {
        "sku": trunc(sku, 120) if sku else None,
        "barcode": None,
        "descripcion": trunc(descripcion, 512) if descripcion else None,
        "familia_id": familia_id,
        "familia_nombre": trunc(familia_nombre, 255) if familia_nombre else None,
        "genero_id": genero_id,
        "genero_descripcion": trunc(genero_descripcion, 255) if genero_descripcion else None,
        "stock_minimo": stock_minimo,
        "frecuencia_mensual": frecuencia_mensual,
    }

def load_payload_raw():
    # Preferimos lo que deja el .sh
    payload_path = os.environ.get("TMP_PAYLOAD_PATH") or os.environ.get("TMP_JSON_PATH")
    if payload_path and os.path.exists(payload_path):
        with open(payload_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    # Fallback: intentar sacar del SOAP guardado
    soapfile = "/tmp/soap_response_articulos.xml"
    if os.path.exists(soapfile):
        with open(soapfile, "r", encoding="utf-8") as f:
            soap_text = f.read()

        m = re.search(r"<MensError>(.*?)</MensError>", soap_text, re.IGNORECASE | re.DOTALL)
        if m and m.group(1).strip():
            msg = m.group(1).strip()
            print(f"[WARN] MensError en ConsArticulosWeb: {msg}")
            return ""

        m2 = re.search(r"<ConsArticulosWebResult>([\s\S]*?)</ConsArticulosWebResult>", soap_text, re.IGNORECASE)
        if m2:
            return m2.group(1).strip()

    return ""

def main():
    payload_raw = load_payload_raw()
    if not payload_raw:
        print("[WARN] payload vacío. No hay artículos a procesar. Salida OK.")
        return 0

    # Decodificar UNA sola capa de entidades (crítico para no romper XML)
    decoded = html.unescape(payload_raw).strip()

    items = []

    # Intentar JSON si parece JSON
    if decoded.startswith("{") or decoded.startswith("["):
        try:
            parsed = json.loads(decoded)
            if isinstance(parsed, dict):
                if isinstance(parsed.get("Rows"), list):
                    parsed = parsed["Rows"]
                elif isinstance(parsed.get("Data"), list):
                    parsed = parsed["Data"]
                else:
                    parsed = [parsed]
            if isinstance(parsed, list):
                items = [x for x in parsed if isinstance(x, dict)]
        except Exception:
            items = []

    # Si no es JSON válido, intentar XML
    if not items:
        if not decoded.startswith("<"):
            # a veces queda con whitespace raro; reintentar si contiene "<Articulos"
            if "<Articulos" in decoded:
                decoded = decoded[decoded.find("<Articulos"):]
        xml_items, err = parse_items_from_xml(decoded)
        if err:
            # si el WS trae <Articulos /> esto NO es error, solo 0 items.
            if "<Articulos" in decoded:
                # intentar parse igual (err) -> log y salir OK
                print(f"[WARN] {err}")
                print("[WARN] No se pudieron parsear artículos desde XML. Salida OK.")
                return 0
            print(f"[WARN] No parece XML ni JSON. {err}")
            return 0
        items = xml_items

    if not items:
        print("[WARN] No se detectaron items de artículos en el payload. Salida OK.")
        return 0

    # Conectar MySQL
    conn = pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DB"],
        autocommit=False,
        charset="utf8mb4",
    )

    insert_sql = """
    INSERT INTO articulos
      (sku, barcode, descripcion, familia_id, familia_nombre, genero_id, genero_descripcion,
       stock_minimo, frecuencia_mensual, fuente, ts_carga)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6))
    ON DUPLICATE KEY UPDATE
      barcode = VALUES(barcode),
      descripcion = VALUES(descripcion),
      familia_id = VALUES(familia_id),
      familia_nombre = VALUES(familia_nombre),
      genero_id = VALUES(genero_id),
      genero_descripcion = VALUES(genero_descripcion),
      stock_minimo = VALUES(stock_minimo),
      frecuencia_mensual = VALUES(frecuencia_mensual),
      fuente = VALUES(fuente),
      actualizado_en = NOW(6),
      ts_carga = NOW(6)
    """

    rows_ins = 0
    rows_skip = 0

    try:
        with conn.cursor() as cur:
            for raw in items:
                normalized = normalize_item(raw)
                if not normalized["sku"]:
                    rows_skip += 1
                    continue

                try:
                    cur.execute(
                        insert_sql,
                        (
                            normalized["sku"],
                            normalized["barcode"],
                            normalized["descripcion"],
                            normalized["familia_id"],
                            normalized["familia_nombre"],
                            normalized["genero_id"],
                            normalized["genero_descripcion"],
                            normalized["stock_minimo"],
                            normalized["frecuencia_mensual"],
                            "ConsArticulosWeb",
                        ),
                    )
                    rows_ins += 1
                except Exception:
                    rows_skip += 1
            conn.commit()
    finally:
        conn.close()

    print(f"[INFO] Inserted/Upserted {rows_ins} articulos (skipped {rows_skip})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
