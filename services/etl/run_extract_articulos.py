#!/usr/bin/env python3
# run_extract_articulos.py - extracción (segundo script) + inserción (primer script, BUG corregido)
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

    # Recorrer todo y aceptar 'Articulo' en cualquier case/namespaces
    for el in root.iter():
        if localname(el.tag).lower() == "articulo":
            d = {}
            for c in list(el):
                k = localname(c.tag)
                v = c.text.strip() if c.text is not None else None
                d[k] = v
            if d:
                items.append(d)

    return items, None

def normalize_sku_from_item(it: dict):
    raw = (
        it.get("IdArticulo")
        or it.get("SKU")
        or it.get("Articulo")
        or it.get("Codigo")
        or it.get("Id")
    )
    if raw is None:
        return None
    s = str(raw)
    # remove control chars
    s = "".join(ch for ch in s if ord(ch) >= 32)
    # collapse whitespace
    s = " ".join(s.split())
    s = s.strip().upper()
    if s == "":
        return None
    return s[:128]

def normalize_item(it: dict):
    # Tomamos los campos reales del WS (segundo script) y añadimos las columnas del modelo (primer script)
    sku = normalize_sku_from_item(it)

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

    seccion_id = to_int_nullable(it.get("IdSeccion") or it.get("SeccionId"))
    seccion_nombre = it.get("DescSeccion") or it.get("Seccion")

    marca_id = to_int_nullable(it.get("IdMarca") or it.get("MarcaId"))
    marca_nombre = it.get("DescMarca") or it.get("Marca")

    temporada_id = to_int_nullable(it.get("IdTemporada") or it.get("TemporadaId"))
    temporada_nombre = it.get("DescTemporada") or it.get("Temporada")

    # Fechas y comentarios (se dejan como strings truncadas)
    fec_alta = it.get("FecAlta") or it.get("FechaAlta") or it.get("FecAltaArt")
    fec_modif = it.get("FecModif") or it.get("FecModifArt") or it.get("FechaModificacion")
    comentario = it.get("Comentario") or it.get("Observacion")

    fact_desc_min = it.get("FactDescMin") or it.get("FactDescMinimo") or it.get("FactDescMinima")
    fact_desc_max = it.get("FactDescMax") or it.get("FactDescMaximo") or it.get("FactDescMaxima")
    desc_valida = it.get("DescValida")

    stock_minimo = to_nonneg_int(it.get("StockMinimo") or it.get("MinStock") or it.get("StockMinimoArt"), 0)
    frecuencia_mensual = to_int_nullable(it.get("FrecuenciaMensual"))

    return {
        "sku": trunc(sku, 128) if sku else None,
        "descripcion": trunc(descripcion, 512) if descripcion else None,
        "familia_id": familia_id,
        "familia_nombre": trunc(familia_nombre, 255) if familia_nombre else None,
        "genero_id": genero_id,
        "genero_descripcion": trunc(genero_descripcion, 255) if genero_descripcion else None,
        "seccion_id": seccion_id,
        "seccion_nombre": trunc(seccion_nombre, 255) if seccion_nombre else None,
        "marca_id": marca_id,
        "marca_nombre": trunc(marca_nombre, 255) if marca_nombre else None,
        "temporada_id": temporada_id,
        "temporada_nombre": trunc(temporada_nombre, 255) if temporada_nombre else None,
        "fec_alta": trunc(fec_alta, 19) if fec_alta else None,
        "fec_modif": trunc(fec_modif, 19) if fec_modif else None,
        "comentario": trunc(comentario, 1024) if comentario else None,
        "fact_desc_min": trunc(fact_desc_min, 32) if fact_desc_min else None,
        "fact_desc_max": trunc(fact_desc_max, 32) if fact_desc_max else None,
        "desc_valida": trunc(desc_valida, 16) if desc_valida else None,
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
            if "<Articulos" in decoded:
                decoded = decoded[decoded.find("<Articulos"):]
        xml_items, err = parse_items_from_xml(decoded)
        if err:
            if "<Articulos" in decoded:
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

    # NOTE: ts_carga se setea con NOW(6) para evitar mismatch de placeholders
    insert_sql = """
    INSERT INTO articulos
      (sku, descripcion, familia_id, familia_nombre, genero_id, genero_descripcion,
       seccion_id, seccion_nombre, marca_id, marca_nombre, temporada_id, temporada_nombre,
       fec_alta, fec_modif, comentario, fact_desc_min, fact_desc_max, desc_valida,
       stock_minimo, frecuencia_mensual, fuente, ts_carga)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6))
    ON DUPLICATE KEY UPDATE
      descripcion = VALUES(descripcion),
      familia_id = VALUES(familia_id),
      familia_nombre = VALUES(familia_nombre),
      genero_id = VALUES(genero_id),
      genero_descripcion = VALUES(genero_descripcion),
      seccion_id = VALUES(seccion_id),
      seccion_nombre = VALUES(seccion_nombre),
      marca_id = VALUES(marca_id),
      marca_nombre = VALUES(marca_nombre),
      temporada_id = VALUES(temporada_id),
      temporada_nombre = VALUES(temporada_nombre),
      fec_alta = VALUES(fec_alta),
      fec_modif = VALUES(fec_modif),
      comentario = VALUES(comentario),
      fact_desc_min = VALUES(fact_desc_min),
      fact_desc_max = VALUES(fact_desc_max),
      desc_valida = VALUES(desc_valida),
      stock_minimo = VALUES(stock_minimo),
      frecuencia_mensual = VALUES(frecuencia_mensual),
      fuente = VALUES(fuente),
      actualizado_en = NOW(6),
      ts_carga = NOW(6)
    """

    rows_ins = 0
    rows_skip = 0
    skipped_samples = []
    err_log = []

    try:
        with conn.cursor() as cur:
            for idx, raw in enumerate(items):
                normalized = normalize_item(raw)
                if not normalized["sku"]:
                    rows_skip += 1
                    if len(skipped_samples) < 20:
                        keys = list(raw.keys())
                        summary = {k:(raw[k][:120]+'...' if isinstance(raw[k],str) and len(raw[k])>120 else raw[k]) for k in keys[:16]}
                        skipped_samples.append({"index": idx, "summary": summary})
                    continue

                try:
                    cur.execute(
                        insert_sql,
                        (
                            normalized["sku"],
                            normalized["descripcion"],
                            normalized["familia_id"],
                            normalized["familia_nombre"],
                            normalized["genero_id"],
                            normalized["genero_descripcion"],
                            normalized["seccion_id"],
                            normalized["seccion_nombre"],
                            normalized["marca_id"],
                            normalized["marca_nombre"],
                            normalized["temporada_id"],
                            normalized["temporada_nombre"],
                            normalized["fec_alta"],
                            normalized["fec_modif"],
                            normalized["comentario"],
                            normalized["fact_desc_min"],
                            normalized["fact_desc_max"],
                            normalized["desc_valida"],
                            normalized["stock_minimo"],
                            normalized["frecuencia_mensual"],
                            "ConsArticulosWeb",
                        ),
                    )
                    rows_ins += 1
                except Exception as e:
                    rows_skip += 1
                    err_log.append({"index": idx, "sku": normalized.get("sku"), "error": str(e), "normalized": normalized, "raw_keys": list(raw.keys())})
            conn.commit()
    finally:
        conn.close()

    # Guardar muestras y errores para debugging
    if skipped_samples:
        try:
            with open("/tmp/articulos_skipped_samples.json","w",encoding="utf-8") as f:
                json.dump({"skipped_count": rows_skip, "samples": skipped_samples}, f, ensure_ascii=False, indent=2)
            print(f"[WARN] Guardadas muestras de items skippeados en /tmp/articulos_skipped_samples.json (muestras: {len(skipped_samples)})")
        except Exception:
            pass

    if err_log:
        try:
            with open("/tmp/articulos_insert_errors.log","w",encoding="utf-8") as f:
                for e in err_log:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
            print(f"[ERROR] Errores de inserción registrados en /tmp/articulos_insert_errors.log (count: {len(err_log)})")
        except Exception:
            pass

    print(f"[INFO] Inserted/Upserted {rows_ins} articulos (skipped {rows_skip})")
    return 0

if __name__ == "__main__":
    sys.exit(main())