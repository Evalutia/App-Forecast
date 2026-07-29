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
