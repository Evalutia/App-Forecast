#!/usr/bin/env python3
"""Parsers compartidos por los extractores del ETL (Issue #125).

Antes cada extractor (stockxml, sales_chunk, articulos) reimplementaba su
propia variante de numeros/fechas/codigos y las variantes divergian en
silencio -- ver .claude/CONTEXTO.md, seccion #125, para el detalle de cada
bug (el mas grave: sales_chunk perdia el signo/valor real de una venta
ante '1.234' o '1,5' y lo pisaba con un 0 que ademas sobreescribia stock
correcto ya cargado por el otro extractor).
"""
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

FORMATOS_FECHA = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
)


class ParseError(ValueError):
    """Un valor no vacio no pudo interpretarse.

    A diferencia del codigo que reemplaza, esto nunca se traduce a un 0 (o
    a un None) en silencio: el caller decide como registrar el fallo de
    forma visible (log + fila salteada), no se pierde en un try/except mudo.
    """


def parse_decimal(valor):
    """Normaliza numeros como los manda el web service.

    Formatos observados: '25.000' / '3.800.000' (puntos como separador de
    miles -- heuristica: mas de un punto implica que son miles, se
    remueven), '1,5' (coma como separador decimal), enteros y floats
    nativos. None o '' -> None (ausencia de dato, no un fallo). Cualquier
    otro valor no interpretable levanta ParseError.
    """
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise ParseError(f"valor booleano no interpretable como numero: {valor!r}")
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    s = str(valor).strip()
    if s == "":
        return None
    s = s.replace(",", ".")
    if s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        raise ParseError(f"numero no interpretable: {valor!r}")


def redondear(valor: float, decimales: int) -> float:
    """Redondea con ROUND_HALF_UP -- Issue #182: el round() nativo de Python
    redondea al par mas cercano ("banker's rounding"), round(2.675, 2) ==
    2.67, no 2.68. Mismo criterio que parse_entero() ya usa para enteros
    (mas abajo), expuesto para columnas con decimales de run_calc_planilla.py/
    run_calc_sugerencias.py -- el caso `promedio` de valor_ajustado
    ((historico + valor_no_historico) / 2) produce medios centavos
    seguido, con un sesgo sistemico de banker's rounding en una columna que
    el cliente ve directo.

    Decimal(str(valor)), no Decimal(valor): un float como 2.675 no es
    exactamente representable en binario (es en verdad
    2.67499999999999982...), así que Decimal(valor) redondearia distinto
    de lo que un humano escribiria a mano -- mismo motivo por el que
    parse_decimal() ya hace Decimal(str(x)) en vez de Decimal(x) directo.
    """
    return float(Decimal(str(valor)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP))


def parse_entero(valor, *, signed=False, default=0, contexto=None):
    """Entero redondeado a partir de parse_decimal.

    None/'' -> default. Si signed=False (caso por defecto: cantidades de
    stock, nunca negativas) un resultado negativo se recorta a 0 -- esa es
    una regla de negocio deliberada, no un fallo de parseo, y se preserva
    tal cual la tenian los extractores originales. Un valor realmente no
    interpretable (p. ej. 'abc') levanta ParseError, nunca cae a 0.

    Un clamp real (negativo -> 0) deja rastro en el log (Issue #156): antes
    ese 0 era indistinguible de un 0 real del WS. No cambia el valor
    persistido ni afecta al camino signed=True (donde el negativo es
    legitimo, ver #80). `contexto` es opcional -- si el caller ya sabe
    sku/fecha de la fila, lo pasa para que el WARN quede tan identificable
    como los demas WARN de fila descartada.
    """
    d = parse_decimal(valor)
    if d is None:
        return default
    n = int(d.to_integral_value(rounding=ROUND_HALF_UP))
    if not signed and n < 0:
        sufijo = f" {contexto}" if contexto else ""
        print(f"[WARN] parse_entero: valor negativo real recortado a 0 (valor original={valor!r}, interpretado={n}){sufijo}")
        n = 0
    return n


def parse_fecha(valor):
    """Fecha 'YYYY-MM-DD' a partir de cualquiera de los formatos observados
    en el web service (incluye el separador con espacio en vez de 'T', que
    ningun extractor aceptaba antes). None/'' -> None. No interpretable, o
    fuera del rango 1900-2100, levanta ParseError.
    """
    if not valor:
        return None
    s = str(valor).strip()
    if s == "":
        return None
    candidato = s[:19]
    for fmt in FORMATOS_FECHA:
        try:
            d = dt.datetime.strptime(candidato, fmt)
        except ValueError:
            continue
        if d.year < 1900 or d.year > 2100:
            raise ParseError(f"fecha fuera de rango: {valor!r}")
        return d.strftime("%Y-%m-%d")
    raise ParseError(f"fecha no interpretable: {valor!r}")


def normalize_sku(valor):
    """Normaliza codigos de articulo: quita caracteres de control, colapsa
    espacios (extremos e internos), pasa a mayusculas, trunca a 128 chars.
    None, o vacio tras normalizar, -> None.
    """
    if valor is None:
        return None
    s = str(valor)
    s = "".join(ch for ch in s if ord(ch) >= 32)
    s = " ".join(s.split())
    s = s.strip().upper()
    if s == "":
        return None
    return s[:128]
