"""Fixtures de payloads reales del web service (Issue #125).

Formatos observados en produccion, documentados en .claude/CONTEXTO.md y en
los extractores existentes antes de la unificacion:
- Numeros: '25.000' / '3.800.000' (punto como separador de miles cuando hay
  mas de un grupo), '1,5' (coma como separador decimal).
- Fechas: ISO con 'T', ISO con espacio, 'dd/mm/aaaa', 'dd-mm-aaaa'.
- Codigos de articulo: con espacios de borde/internos y minusculas mezcladas.
"""

NUMEROS_MILES = ["25.000", "3.800.000", "1.200"]
NUMEROS_DECIMALES_COMA = ["1,5", "0,5", "-3,25"]
NUMEROS_NULOS = [None, "", "   "]
NUMEROS_CERO = ["0", 0, "0,0"]
NUMEROS_NEGATIVOS = ["-3", -3, "-3,25"]
NUMEROS_NO_INTERPRETABLES = ["abc", "N/D", "--", "1.2.3.abc"]

FECHAS_POR_FORMATO = {
    "%Y-%m-%dT%H:%M:%S": "2026-08-01T14:30:00",
    "%Y-%m-%d %H:%M:%S": "2026-08-01 14:30:00",
    "%Y-%m-%d": "2026-08-01",
    "%d/%m/%Y": "01/08/2026",
    "%d-%m-%Y": "01-08-2026",
}
FECHAS_NO_INTERPRETABLES = ["31/13/2026", "no-es-fecha", "2026/08/01"]

CODIGOS_ARTICULO = {
    " abc123 ": "ABC123",
    "abc  123": "ABC 123",
    "\tABC123\n": "ABC123",
    "abc\x00123": "ABC123",
}

# Item de venta tal como lo devuelve ConsStockVenta (mismo shape que usa
# test_run_extract_sales_chunk.py::_item).
ITEM_VENTA_MILES = {"Fecha": "2026-08-01", "IdArticulo": "SKU1", "Venta": "1.200", "Stock": "3.800.000"}
ITEM_VENTA_DECIMAL_COMA = {"Fecha": "2026-08-01", "IdArticulo": "SKU1", "Venta": "1,5", "Stock": "25.000"}
