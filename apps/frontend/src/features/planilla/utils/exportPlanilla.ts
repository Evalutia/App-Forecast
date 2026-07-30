import ExcelJS, { type Cell } from 'exceljs';
import { fetchPlanillaVentas } from './api';
import type { PlanillaMesDto, PlanillaSugerenciaDto, PlanillaVentasDto, PlanillaVentasParams } from '../types/planilla';

const MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const mesLabel = (year: number, month: number) => `${MESES[month - 1]}/${String(year).slice(2)}`;

// Cell background colors matching the UI (issue #28)
const COLOR_QUIEBRE_ALTA  = 'FFCA28'; // amber — alta frecuencia
const COLOR_QUIEBRE_MEDIA = 'FFB74D'; // orange — media frecuencia
const COLOR_QUIEBRE_BAJA  = 'EF9A9A'; // rose — baja frecuencia
const COLOR_SINSTOCK      = '90A4AE'; // slate grey
const COLOR_SINDATOS      = 'F1F5F9'; // light slate — mes sin fila calculada (#106)
const COLOR_HEADER        = '0D5C2E'; // dark green for headers
const COLOR_SUMMARY       = '1B4332'; // darker green for summary col headers
const COLOR_SUMMARY_BG    = 'D1FAE5'; // light green for summary data cells
const COLOR_SUMMARY_FG    = '065F46'; // dark green text for summary data cells

// Issue #107: fondo por criterio de frecuencia en las celdas VAj de la hoja 2.
// Paleta fría de #65 (azul/violeta/teal), tintes claros para celda de Excel —
// deliberadamente lejos del amarillo/naranja/rojo/gris de quiebre.
const CRITERIO_FILL: Record<string, { bg: string; fg: string }> = {
  historico:        { bg: 'BFDBFE', fg: '1E3A8A' }, // azul
  promedio:         { bg: 'DDD6FE', fg: '4C1D95' }, // violeta
  real_extrapolado: { bg: '99F6E4', fg: '134E4A' }, // teal
};

function mesBgColor(estadoMes: string, frecuenciaNivel?: string | null): string | null {
  if (estadoMes === 'quiebre_parcial') {
    if (frecuenciaNivel === 'baja')  return COLOR_QUIEBRE_BAJA;
    if (frecuenciaNivel === 'media') return COLOR_QUIEBRE_MEDIA;
    return COLOR_QUIEBRE_ALTA;
  }
  if (estadoMes === 'sin_stock') return COLOR_SINSTOCK;
  if (estadoMes === 'sin_datos') return COLOR_SINDATOS;
  return null;
}

function mesFgColor(estadoMes: string, frecuenciaNivel?: string | null): string {
  if (estadoMes === 'quiebre_parcial') {
    return frecuenciaNivel === 'baja' ? 'FF7F1D1D' : 'FF7B4A00';
  }
  if (estadoMes === 'sin_stock') return 'FF374151';
  return 'FF111827';
}

function applyMesStyle(cell: Cell, mes: PlanillaMesDto, isRef: boolean): void {
  const bg = mesBgColor(mes.estadoMes, mes.frecuenciaNivel);
  if (bg) {
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: `FF${bg}` } };
    cell.font = { color: { argb: mesFgColor(mes.estadoMes, mes.frecuenciaNivel) }, size: 10 };
  } else if (isRef) {
    cell.font = { color: { argb: 'FF6B7280' }, italic: true, size: 10 };
  } else {
    cell.font = { size: 10 };
  }
  cell.alignment = { vertical: 'middle', horizontal: 'right' };
  cell.border    = { right: { style: 'hair', color: { argb: 'FFD1D5DB' } } };
}

function applySummaryStyle(cell: Cell, numFmt: string): void {
  cell.numFmt    = numFmt;
  cell.alignment = { horizontal: 'right', vertical: 'middle' };
  cell.font      = { bold: true, size: 10, color: { argb: `FF${COLOR_SUMMARY_FG}` } };
  cell.fill      = { type: 'pattern', pattern: 'solid', fgColor: { argb: `FF${COLOR_SUMMARY_BG}` } };
}

function applyHeaderStyle(headerRow: ExcelJS.Row, firstSummaryCol: number): void {
  headerRow.height = 22;
  headerRow.eachCell((cell: Cell, colNum: number) => {
    const isSummary = colNum >= firstSummaryCol;
    cell.fill      = { type: 'pattern', pattern: 'solid', fgColor: { argb: `FF${isSummary ? COLOR_SUMMARY : COLOR_HEADER}` } };
    cell.font      = { bold: true, color: { argb: 'FFFFFFFF' }, size: 10 };
    cell.alignment = { vertical: 'middle', horizontal: colNum <= 2 ? 'left' : 'center', wrapText: false };
    cell.border    = { bottom: { style: 'medium', color: { argb: 'FF34C48F' } } };
  });
}

function rotDesEstac(meses: PlanillaMesDto[]): number | null {
  const closed = meses.slice(0, -1);
  const vals: number[] = [];
  for (const m of closed) {
    if (m.estadoMes === 'normal' && m.rotacionDiariaDesestacionalizada != null) {
      vals.push(m.rotacionDiariaDesestacionalizada);
    } else if (m.estadoMes === 'quiebre_parcial' && m.rotacionAjustada != null) {
      if (m.rotacionDiariaDesestacionalizada != null && m.rotacionDiariaReal != null && m.rotacionDiariaReal > 0)
        vals.push(m.rotacionAjustada * (m.rotacionDiariaDesestacionalizada / m.rotacionDiariaReal));
      else
        vals.push(m.rotacionAjustada);
    }
  }
  return vals.length === 0 ? null : vals.reduce((s, v) => s + v, 0) / vals.length;
}

function ddstk(meses: PlanillaMesDto[]): number | null {
  const totalVentas = meses.reduce((s, m) => s + (m.ventasCantidad ?? 0), 0);
  const totalDias   = meses.reduce((s, m) => s + (m.diasConStock ?? 0), 0);
  return totalDias === 0 ? null : totalVentas / totalDias;
}

// Issue #66: "VentaReal/Extrapolación" no esta persistido por separado en #62
// (solo valor_ajustado y criterio_frecuencia) -- se reconstruye con datos ya
// expuestos, misma formula exacta que run_calc_planilla.py (Extrapolacion =
// rotacion_diaria_real * dias_naturales_mes). Si es sin_stock (rotacionDiariaReal
// null, extrapolacion indefinida), no hubo componente real que usar en el
// blend para esa fila -- se deja en blanco, no se inventa un valor.
function ventaRealOExtrapolacion(mes: PlanillaMesDto): number | null {
  if (mes.estadoMes === 'normal') return mes.ventasCantidad ?? 0;
  if (mes.rotacionDiariaReal != null) return mes.rotacionDiariaReal * mes.diasNaturalesMes;
  return null;
}

// Issue #66: etiqueta legible del criterio (mismo criterio que #65 en
// PlanillaTable.tsx) -- el Excel lo lee el cliente directo, no un programador.
function criterioFrecuenciaLabel(criterio: string | null | undefined, estadoMes: string): string {
  if (criterio === 'historico') return 'Histórico';
  if (criterio === 'promedio')  return 'Promedio';
  if (criterio === 'real_extrapolado') return estadoMes === 'normal' ? 'Venta real' : 'Extrapolado';
  return '';
}

// ── Hoja 1: "Planilla de Reposición" ─────────────────────────────────────────
// Issue #107: layout idéntico a la planilla original del cliente (hoja "Ventas"
// de su .xlsm), con sus nombres exactos de header, + nuestros agregados a la
// derecha. Sin SIN STOCK / TOT STK / C/STK / Rot. Manual (decisión #33).
function buildHojaPlanilla(
  wb: ExcelJS.Workbook,
  items: PlanillaVentasDto[],
  sugerencias: Map<string, PlanillaSugerenciaDto>,
): void {
  const ws = wb.addWorksheet('Planilla de Reposición', {
    views: [{ state: 'frozen', xSplit: 1, ySplit: 1 }],
  });

  const meses      = items[0].meses;
  const n          = meses.length;
  const lastMesIdx = n - 1;
  const mesLabels  = meses.map(m => mesLabel(m.year, m.month));

  // Column index helpers (1-based).
  // Bloque del cliente: Articulo, Descripcion, Codigos Barras, Vta×n, Rot×n
  // (meses a secas, su convención), Rotacion DesEstac., Estado Art., VTA, DDSTK.
  // Bloque nuestro: ROT.S, Fiabilidad %, QBK (días), Género.
  const COL_VTA_MES = (i: number) => 4 + i;
  const COL_ROT_MES = (i: number) => 4 + n + i;
  const COL_RD      = 4 + 2 * n;
  const COL_ESTADO  = 5 + 2 * n;
  const COL_VTA     = 6 + 2 * n;
  const COL_DD      = 7 + 2 * n;
  const COL_ROTS    = 8 + 2 * n;
  const COL_FIAB    = 9 + 2 * n;
  const COL_QBK     = 10 + 2 * n;
  const COL_GENERO  = 11 + 2 * n;

  const headers = [
    'Articulo',
    'Descripcion',
    'Codigos Barras',
    ...mesLabels.map(l => `Vta.${l}`),
    ...mesLabels,
    'Rotacion DesEstac.',
    'Estado Art.',
    'VTA',
    'DDSTK',
    'ROT.S',
    'Fiabilidad %',
    'QBK (días)',
    'Género',
  ];

  ws.columns = [
    { width: 13 },                                              // Articulo
    { width: 34 },                                              // Descripcion
    { width: 18 },                                              // Codigos Barras
    ...meses.map((_, i) => ({ width: i === lastMesIdx ? 10 : 9 })),  // Vta months
    ...meses.map((_, i) => ({ width: i === lastMesIdx ? 10 : 9 })),  // Rot months
    { width: 17 },                                              // Rotacion DesEstac.
    { width: 12 },                                              // Estado Art.
    { width: 10 },                                              // VTA
    { width: 12 },                                              // DDSTK
    { width: 10 },                                              // ROT.S
    { width: 13 },                                              // Fiabilidad %
    { width: 11 },                                              // QBK
    { width: 18 },                                              // Género
  ];

  applyHeaderStyle(ws.addRow(headers), COL_RD);

  for (const item of items) {
    const sug = sugerencias.get(item.sku);
    const row = ws.addRow([
      item.sku,
      item.descripcion ?? '',
      item.codigoBarras ?? '',
      // Meses sin_datos (#106) exportan celda vacía (null), no un 0 inventado.
      ...item.meses.map(m => m.ventasCantidad),
      ...item.meses.map(m => m.estadoMes === 'sin_datos' ? null : m.rotacionDiariaReal ?? 0),
      rotDesEstac(item.meses),
      item.estadoArticulo ?? 'activo',
      item.meses.slice(0, -1).reduce((s, m) => s + (m.ventasCantidad ?? 0), 0),
      ddstk(item.meses),
      sug?.rotacionSugerida ?? null,
      sug?.fiabilidadPorcentaje ?? null,
      sug?.diasHastaQuiebre != null ? Math.round(sug.diasHastaQuiebre) : null,
      item.generoDescripcion ?? '',
    ]);
    row.height = 18;

    row.getCell(1).font      = { bold: true, size: 10 };
    row.getCell(1).alignment = { vertical: 'middle' };

    item.meses.forEach((mes, i) => {
      const vta = row.getCell(COL_VTA_MES(i));
      vta.numFmt = '#,##0';
      applyMesStyle(vta, mes, i === lastMesIdx);

      const rot = row.getCell(COL_ROT_MES(i));
      rot.numFmt = '0.0000';
      applyMesStyle(rot, mes, i === lastMesIdx);
    });

    applySummaryStyle(row.getCell(COL_RD),   '0.0000');
    applySummaryStyle(row.getCell(COL_VTA),  '#,##0');
    applySummaryStyle(row.getCell(COL_DD),   '0.0000');
    applySummaryStyle(row.getCell(COL_ROTS), '0.0000');
    applySummaryStyle(row.getCell(COL_FIAB), '0.0"%"');
    applySummaryStyle(row.getCell(COL_QBK),  '0');
    row.getCell(COL_ESTADO).font      = { size: 10 };
    row.getCell(COL_ESTADO).alignment = { vertical: 'middle', horizontal: 'center' };
    row.getCell(COL_GENERO).font      = { size: 10 };
  }
}

// ── Hoja 2: "Detalle de cálculo" ─────────────────────────────────────────────
// Issue #107: los 5 bloques mensuales del blending de frecuencia (#61/#63/#66)
// se mudan acá para descomprimir la hoja principal. VAj lleva fondo por
// criterio (leyenda arriba); el resto conserva el color de quiebre.
function buildHojaDetalle(wb: ExcelJS.Workbook, items: PlanillaVentasDto[]): void {
  const ws = wb.addWorksheet('Detalle de cálculo', {
    views: [{ state: 'frozen', xSplit: 2, ySplit: 3 }],
  });

  const meses      = items[0].meses;
  const n          = meses.length;
  const lastMesIdx = n - 1;
  const mesLabels  = meses.map(m => mesLabel(m.year, m.month));

  const COL_TICK = (i: number) => 3 + i;
  const COL_HIST = (i: number) => 3 + n + i;
  const COL_VE   = (i: number) => 3 + 2 * n + i;
  const COL_CRIT = (i: number) => 3 + 3 * n + i;
  const COL_VAJ  = (i: number) => 3 + 4 * n + i;

  ws.columns = [
    { width: 13 },                            // Articulo
    { width: 34 },                            // Descripcion
    ...meses.map(() => ({ width: 8 })),       // Tick
    ...meses.map(() => ({ width: 9 })),       // Hist
    ...meses.map(() => ({ width: 9 })),       // V/E
    ...meses.map(() => ({ width: 12 })),      // Crit (texto)
    ...meses.map(() => ({ width: 9 })),       // VAj
  ];

  // Leyenda del color por criterio (fila 1), antes del header (fila 3).
  const leyenda = ws.getRow(1);
  leyenda.height = 20;
  leyenda.getCell(1).value = 'Método del valor ajustado (VAj):';
  leyenda.getCell(1).font  = { bold: true, size: 10 };
  const chips: [string, string][] = [
    ['historico', 'Histórico'],
    ['promedio', 'Promedio'],
    ['real_extrapolado', 'Venta real / Extrapolado'],
  ];
  chips.forEach(([criterio, label], i) => {
    const start = 3 + i * 3;
    ws.mergeCells(1, start, 1, start + 2);
    const cell = ws.getCell(1, start);
    cell.value     = label;
    cell.fill      = { type: 'pattern', pattern: 'solid', fgColor: { argb: `FF${CRITERIO_FILL[criterio].bg}` } };
    cell.font      = { size: 10, color: { argb: `FF${CRITERIO_FILL[criterio].fg}` } };
    cell.alignment = { horizontal: 'center', vertical: 'middle' };
  });

  ws.addRow([]); // fila 2: separador

  const headers = [
    'Articulo',
    'Descripcion',
    ...mesLabels.map(l => `Tick.${l}`),
    ...mesLabels.map(l => `Hist.${l}`),
    ...mesLabels.map(l => `V/E.${l}`),
    ...mesLabels.map(l => `Crit.${l}`),
    ...mesLabels.map(l => `VAj.${l}`),
  ];
  applyHeaderStyle(ws.addRow(headers), headers.length + 1); // sin bloque summary

  for (const item of items) {
    const row = ws.addRow([
      item.sku,
      item.descripcion ?? '',
      ...item.meses.map(m => m.ticketsMes),
      ...item.meses.map(m => m.valorHistorico ?? null),
      ...item.meses.map(m => ventaRealOExtrapolacion(m)),
      ...item.meses.map(m => criterioFrecuenciaLabel(m.criterioFrecuencia, m.estadoMes)),
      ...item.meses.map(m => m.valorAjustado ?? null),
    ]);
    row.height = 18;

    row.getCell(1).font      = { bold: true, size: 10 };
    row.getCell(1).alignment = { vertical: 'middle' };

    item.meses.forEach((mes, i) => {
      const isRef = i === lastMesIdx;
      const tick = row.getCell(COL_TICK(i));
      tick.numFmt = '0';
      applyMesStyle(tick, mes, isRef);

      const hist = row.getCell(COL_HIST(i));
      hist.numFmt = '#,##0.00';
      applyMesStyle(hist, mes, isRef);

      const ve = row.getCell(COL_VE(i));
      ve.numFmt = '#,##0.00';
      applyMesStyle(ve, mes, isRef);

      applyMesStyle(row.getCell(COL_CRIT(i)), mes, isRef);

      // VAj: el color señala el MÉTODO (leyenda de la fila 1), no el quiebre.
      const vaj = row.getCell(COL_VAJ(i));
      vaj.numFmt = '#,##0.00';
      applyMesStyle(vaj, mes, isRef);
      const crit = mes.criterioFrecuencia != null ? CRITERIO_FILL[mes.criterioFrecuencia] : undefined;
      if (crit) {
        vaj.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: `FF${crit.bg}` } };
        vaj.font = { size: 10, color: { argb: `FF${crit.fg}` } };
      }
    });
  }
}

// ── Hoja 3: "Criterios" ──────────────────────────────────────────────────────
// Issue #109: qué significa y cómo se calcula cada columna de las hojas 1-2.
// Contenido estático destilado de las fórmulas VERIFICADAS contra producción
// en la QA de #108 (scripts/qa_planilla_oracle.py) — viaja en cada export.
// Lenguaje para el cliente: sin nombres de tablas ni jerga interna.

// "[mes]" representa cada uno de los 13 meses de la ventana (12 cerrados + el
// mes en curso). exportado tal cual en la hoja; los tests mapean los headers
// reales contra estas filas normalizando la parte del mes.
type CriterioRow = { col: string; hoja: string; que: string; como: string };

export const CRITERIOS_COLUMNAS: CriterioRow[] = [
  // Hoja 1 — Planilla de Reposición
  { col: 'Articulo', hoja: 'Planilla', que: 'Código del artículo.', como: 'Identificador del catálogo.' },
  { col: 'Descripcion', hoja: 'Planilla', que: 'Descripción del artículo.', como: 'Tal como figura en el catálogo.' },
  { col: 'Codigos Barras', hoja: 'Planilla', que: 'Código de barras.', como: 'Tal como figura en el catálogo. Vacío si el artículo no tiene.' },
  { col: 'Vta.[mes]', hoja: 'Planilla', que: 'Unidades vendidas en ese mes (ventas netas: descuenta devoluciones).',
    como: 'Suma de las ventas del mes. La columna de más a la derecha es el mes en curso (incompleto), en letra gris. Celda vacía gris claro = sin datos de ese mes (ej. artículo dado de alta después).' },
  { col: '[mes]', hoja: 'Planilla', que: 'Rotación diaria real del mes: a qué ritmo se vendió mientras hubo stock.',
    como: 'Unidades vendidas del mes ÷ días del mes con stock disponible. Vacía si el mes no tuvo ningún día con stock.' },
  { col: 'Rotacion DesEstac.', hoja: 'Planilla', que: 'Rotación diaria promedio del año, corregida por estacionalidad.',
    como: 'Promedio sobre los 12 meses cerrados: los meses con stock completo usan su rotación ÷ factor estacional del mes; los meses con quiebre usan la rotación ajustada por frecuencia; los meses sin stock o sin datos no participan. Excluye el mes en curso.' },
  { col: 'Estado Art.', hoja: 'Planilla', que: 'Estado del artículo en el catálogo.', como: 'activo (en venta normal), inactivo (temporalmente inactivo) o discontinuo (sin reposición futura).' },
  { col: 'VTA', hoja: 'Planilla', que: 'Total de unidades vendidas en el año.', como: 'Suma de las ventas de los 12 meses cerrados. Excluye el mes en curso.' },
  { col: 'DDSTK', hoja: 'Planilla', que: 'Demanda diaria con stock: venta promedio por día en los días que hubo stock.',
    como: 'Suma de ventas de los 13 meses ÷ suma de días con stock de los 13 meses.' },
  { col: 'ROT.S', hoja: 'Planilla', que: 'Rotación diaria sugerida para planificar la reposición.',
    como: 'Promedio ponderado de la rotación de hasta 13 meses cerrados con datos útiles (stock completo: rotación real; quiebre: rotación ajustada). Los meses recientes pesan más que los antiguos. Vacía si hay menos de 3 meses útiles.' },
  { col: 'Fiabilidad %', hoja: 'Planilla', que: 'Qué tan estable es la rotación del artículo — cuánto confiar en ROT.S.',
    como: '100% = rotación idéntica todos los meses; baja cuanto más varía de mes a mes. Siempre entre 0% y 100%.' },
  { col: 'QBK (días)', hoja: 'Planilla', que: 'Días estimados hasta quedarse sin stock.', como: 'Stock actual ÷ ROT.S. 0 = ya sin stock.' },
  { col: 'Género', hoja: 'Planilla', que: 'Género del artículo.', como: 'Tal como figura en el catálogo.' },
  // Hoja 2 — Detalle de cálculo
  { col: 'Tick.[mes]', hoja: 'Detalle', que: 'Tickets: cantidad de días de ese mes con al menos una venta real.',
    como: 'Se cuentan días con venta, no unidades. Define qué método se usa para el valor ajustado (ver bandas abajo).' },
  { col: 'Hist.[mes]', hoja: 'Detalle', que: 'Histórico: venta mensual promedio del artículo.',
    como: 'Promedio de ventas de los 12 meses cerrados en los que el artículo ya existía. Es el mismo valor en todos los meses de la fila.' },
  { col: 'V/E.[mes]', hoja: 'Detalle', que: 'Venta real del mes, o su extrapolación si hubo quiebre.',
    como: 'Con stock todo el mes: la venta real. Con quiebre: rotación diaria real × días del mes (estima cuánto se habría vendido sin quiebre). Vacía si el mes no tuvo stock.' },
  { col: 'Crit.[mes]', hoja: 'Detalle', que: 'Método usado para el valor ajustado de ese mes.',
    como: 'Histórico, Promedio, Venta real o Extrapolado — según los tickets del mes (ver bandas abajo).' },
  { col: 'VAj.[mes]', hoja: 'Detalle', que: 'Valor ajustado: la estimación de demanda mensual que usa el sistema.',
    como: 'El resultado de aplicar el método de Crit. El color de fondo indica el método (ver leyenda).' },
];

export const CRITERIOS_BANDAS = [
  ['2 tickets o menos', 'Histórico', 'Muy pocas ventas en el mes: la venta puntual no es representativa, se usa el promedio anual.'],
  ['3 a 4 tickets', 'Promedio', 'Zona intermedia: promedio entre el Histórico y la Venta real (o Extrapolación si hubo quiebre).'],
  ['5 tickets o más', 'Venta real / Extrapolado', 'Ventas frecuentes: el propio mes es representativo. Con quiebre se usa la extrapolación.'],
] as const;

const CRITERIOS_COLORES: { color: string | null; fg?: string; label: string; detalle: string }[] = [
  { color: COLOR_QUIEBRE_ALTA, label: 'Amarillo', detalle: 'Mes con quiebre de stock en artículo de alta frecuencia (vendió en 9 o más de los 12 meses).' },
  { color: COLOR_QUIEBRE_MEDIA, label: 'Naranja', detalle: 'Mes con quiebre en artículo de frecuencia media (vendió en 4 a 8 meses).' },
  { color: COLOR_QUIEBRE_BAJA, label: 'Rojo', detalle: 'Mes con quiebre en artículo de baja frecuencia (vendió en 3 meses o menos).' },
  { color: COLOR_SINSTOCK, label: 'Gris', detalle: 'Mes completo sin stock.' },
  { color: COLOR_SINDATOS, label: 'Gris claro', detalle: 'Sin datos: el artículo no existía o no hay información de ese mes. La celda queda vacía.' },
  { color: CRITERIO_FILL.historico.bg, fg: CRITERIO_FILL.historico.fg, label: 'Azul (VAj)', detalle: 'El valor ajustado usó el método Histórico.' },
  { color: CRITERIO_FILL.promedio.bg, fg: CRITERIO_FILL.promedio.fg, label: 'Violeta (VAj)', detalle: 'El valor ajustado usó el método Promedio.' },
  { color: CRITERIO_FILL.real_extrapolado.bg, fg: CRITERIO_FILL.real_extrapolado.fg, label: 'Verde azulado (VAj)', detalle: 'El valor ajustado usó Venta real o Extrapolación.' },
];

function addTituloSeccion(ws: ExcelJS.Worksheet, texto: string): void {
  const row = ws.addRow([texto]);
  row.height = 20;
  const cell = row.getCell(1);
  cell.font = { bold: true, size: 11, color: { argb: `FF${COLOR_SUMMARY_FG}` } };
  ws.mergeCells(row.number, 1, row.number, 4);
}

function buildHojaCriterios(wb: ExcelJS.Workbook): void {
  const ws = wb.addWorksheet('Criterios', { views: [{ state: 'frozen', ySplit: 1 }] });
  ws.columns = [{ width: 22 }, { width: 10 }, { width: 52 }, { width: 78 }];

  applyHeaderStyle(ws.addRow(['Columna', 'Hoja', 'Qué significa', 'Cómo se calcula']), 5);

  const wrap = { vertical: 'top', wrapText: true } as const;
  let hojaActual = '';
  for (const c of CRITERIOS_COLUMNAS) {
    if (c.hoja !== hojaActual) {
      hojaActual = c.hoja;
      addTituloSeccion(ws, hojaActual === 'Planilla'
        ? 'Hoja 1 — Planilla de Reposición'
        : 'Hoja 2 — Detalle de cálculo');
    }
    const row = ws.addRow([c.col, c.hoja, c.que, c.como]);
    row.getCell(1).font = { bold: true, size: 10 };
    [1, 2, 3, 4].forEach(i => { row.getCell(i).alignment = wrap; row.getCell(i).font = { ...row.getCell(i).font, size: 10 }; });
  }

  ws.addRow([]);
  addTituloSeccion(ws, 'Método del valor ajustado según los tickets del mes');
  for (const [banda, metodo, detalle] of CRITERIOS_BANDAS) {
    const row = ws.addRow([banda, '', metodo, detalle]);
    [1, 3, 4].forEach(i => { row.getCell(i).alignment = wrap; row.getCell(i).font = { size: 10 }; });
    row.getCell(3).font = { bold: true, size: 10 };
  }
  const nota = ws.addRow(['', '', '', 'Los umbrales de tickets son los vigentes hoy; pueden ajustarse en la configuración del sistema.']);
  nota.getCell(4).font = { italic: true, size: 9, color: { argb: 'FF6B7280' } };

  ws.addRow([]);
  addTituloSeccion(ws, 'Colores de las celdas mensuales');
  for (const c of CRITERIOS_COLORES) {
    const row = ws.addRow([c.label, '', '', c.detalle]);
    const chip = row.getCell(1);
    if (c.color) {
      chip.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: `FF${c.color}` } };
      chip.font = { size: 10, bold: true, color: { argb: c.fg ? `FF${c.fg}` : 'FF111827' } };
    }
    chip.alignment = { horizontal: 'center', vertical: 'middle' };
    row.getCell(4).alignment = wrap;
    row.getCell(4).font = { size: 10 };
  }
}

// Construcción pura del workbook (testeable en node, sin fetch ni DOM).
export function buildPlanillaWorkbook(
  items: PlanillaVentasDto[],
  sugerencias: Map<string, PlanillaSugerenciaDto>,
): ExcelJS.Workbook {
  const wb = new ExcelJS.Workbook();
  wb.creator  = 'Evalutia';
  wb.modified = new Date();
  buildHojaPlanilla(wb, items, sugerencias);
  buildHojaDetalle(wb, items);
  buildHojaCriterios(wb);
  return wb;
}

async function fetchAll(params: PlanillaVentasParams): Promise<PlanillaVentasDto[]> {
  const first = await fetchPlanillaVentas({ ...params, page: 1, pageSize: 200 });
  const total = first.total;
  if (first.items.length >= total) return first.items;

  const pages = Math.ceil(total / 200);
  const rest  = await Promise.all(
    Array.from({ length: pages - 1 }, (_, i) =>
      fetchPlanillaVentas({ ...params, page: i + 2, pageSize: 200 })
    )
  );
  return [first.items, ...rest.map(r => r.items)].flat();
}

export async function exportPlanillaExcel(
  params: PlanillaVentasParams,
  sugerencias: Map<string, PlanillaSugerenciaDto>,
): Promise<void> {
  const items = await fetchAll(params);
  if (items.length === 0) return;

  const wb = buildPlanillaWorkbook(items, sugerencias);

  const buffer = await wb.xlsx.writeBuffer();
  const blob   = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  const url = URL.createObjectURL(blob);
  const a   = document.createElement('a');
  a.href    = url;
  a.download = `planilla_reposicion_${new Date().toISOString().slice(0, 10)}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}
