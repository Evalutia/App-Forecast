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
const COLOR_HEADER        = '0D5C2E'; // dark green for headers
const COLOR_SUMMARY       = '1B4332'; // darker green for summary col headers
const COLOR_SUMMARY_BG    = 'D1FAE5'; // light green for summary data cells
const COLOR_SUMMARY_FG    = '065F46'; // dark green text for summary data cells

function mesBgColor(estadoMes: string, frecuenciaNivel?: string | null): string | null {
  if (estadoMes === 'quiebre_parcial') {
    if (frecuenciaNivel === 'baja')  return COLOR_QUIEBRE_BAJA;
    if (frecuenciaNivel === 'media') return COLOR_QUIEBRE_MEDIA;
    return COLOR_QUIEBRE_ALTA;
  }
  if (estadoMes === 'sin_stock') return COLOR_SINSTOCK;
  return null;
}

function mesFgColor(estadoMes: string, frecuenciaNivel?: string | null): string {
  if (estadoMes === 'quiebre_parcial') {
    return frecuenciaNivel === 'baja' ? 'FF7F1D1D' : 'FF7B4A00';
  }
  if (estadoMes === 'sin_stock') return 'FF374151';
  return 'FF111827';
}

function applyMesStyle(cell: ExcelJS.Cell, mes: PlanillaMesDto, isRef: boolean): void {
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

function applySummaryStyle(cell: ExcelJS.Cell, numFmt: string): void {
  cell.numFmt    = numFmt;
  cell.alignment = { horizontal: 'right', vertical: 'middle' };
  cell.font      = { bold: true, size: 10, color: { argb: `FF${COLOR_SUMMARY_FG}` } };
  cell.fill      = { type: 'pattern', pattern: 'solid', fgColor: { argb: `FF${COLOR_SUMMARY_BG}` } };
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
  const totalVentas = meses.reduce((s, m) => s + Number(m.ventasCantidad), 0);
  const totalDias   = meses.reduce((s, m) => s + m.diasConStock, 0);
  return totalDias === 0 ? null : totalVentas / totalDias;
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

  const wb = new ExcelJS.Workbook();
  wb.creator  = 'Evalutia';
  wb.modified = new Date();

  const ws = wb.addWorksheet('Planilla de Reposición', {
    views: [{ state: 'frozen', xSplit: 1, ySplit: 1 }],
  });

  // ── Column layout ──────────────────────────────────────────────────────────
  // Fixed (4): SKU, Descripción, Cód.Barras, Género
  // Monthly Vta (n): Vta.Mes/Año × 13
  // Monthly Rot (n): Rot.Mes/Año × 13
  // Summary (7): Rot.DesEstac., Estado, VTA, DDSTK, ROT.S, Fiabilidad%, QBK
  const mesesRef   = items[0].meses;
  const n          = mesesRef.length;
  const lastMesIdx = n - 1;
  const mesLabels  = mesesRef.map(m => mesLabel(m.year, m.month));

  // Column index helpers (1-based)
  const COL_VTA_MES  = (i: number) => 5 + i;          // i = 0..n-1
  const COL_ROT_MES  = (i: number) => 5 + n + i;      // i = 0..n-1
  const COL_RD       = 5 + 2 * n;
  const COL_VTA      = 7 + 2 * n;
  const COL_DD       = 8 + 2 * n;
  const COL_ROTS     = 9 + 2 * n;
  const COL_FIAB     = 10 + 2 * n;
  const COL_QBK      = 11 + 2 * n;

  const headers = [
    'SKU',
    'Descripción',
    'Cód. Barras',
    'Género',
    ...mesLabels.map(l => `Vta.${l}`),
    ...mesLabels.map(l => `Rot.${l}`),
    'Rot. DesEstac.',
    'Estado',
    'VTA',
    'DDSTK',
    'ROT.S',
    'Fiabilidad %',
    'QBK (días)',
  ];

  ws.columns = [
    { width: 13 },                                          // SKU
    { width: 34 },                                          // Descripción
    { width: 18 },                                          // Cód. Barras
    { width: 18 },                                          // Género
    ...mesesRef.map((_, i) => ({ width: i === lastMesIdx ? 10 : 9 })),  // Vta months
    ...mesesRef.map((_, i) => ({ width: i === lastMesIdx ? 10 : 9 })),  // Rot months
    { width: 15 },                                          // Rot. DesEstac.
    { width: 13 },                                          // Estado
    { width: 10 },                                          // VTA
    { width: 12 },                                          // DDSTK
    { width: 10 },                                          // ROT.S
    { width: 13 },                                          // Fiabilidad %
    { width: 11 },                                          // QBK
  ];

  // ── Header row ─────────────────────────────────────────────────────────────
  const headerRow = ws.addRow(headers);
  headerRow.height = 22;
  headerRow.eachCell((cell: Cell, colNum: number) => {
    const isSummary = colNum >= COL_RD;
    cell.fill      = { type: 'pattern', pattern: 'solid', fgColor: { argb: `FF${isSummary ? COLOR_SUMMARY : COLOR_HEADER}` } };
    cell.font      = { bold: true, color: { argb: 'FFFFFFFF' }, size: 10 };
    cell.alignment = { vertical: 'middle', horizontal: colNum <= 2 ? 'left' : 'center', wrapText: false };
    cell.border    = { bottom: { style: 'medium', color: { argb: 'FF34C48F' } } };
  });

  // ── Data rows ──────────────────────────────────────────────────────────────
  for (const item of items) {
    const rd  = rotDesEstac(item.meses);
    const dd  = ddstk(item.meses);
    const vta = item.meses.slice(0, -1).reduce((s, m) => s + Number(m.ventasCantidad), 0);
    const sug = sugerencias.get(item.sku);

    const rowValues = [
      item.sku,
      item.descripcion ?? '',
      item.codigoBarras ?? '',
      item.generoDescripcion ?? '',
      ...item.meses.map(m => Number(m.ventasCantidad)),
      ...item.meses.map(m => m.rotacionDiariaReal ?? 0),
      rd,
      item.estadoArticulo ?? 'activo',
      vta,
      dd,
      sug?.rotacionSugerida ?? null,
      sug?.fiabilidadPorcentaje ?? null,
      sug?.diasHastaQuiebre != null ? Math.round(sug.diasHastaQuiebre) : null,
    ];

    const row = ws.addRow(rowValues);
    row.height = 18;

    row.getCell(1).font      = { bold: true, size: 10 };
    row.getCell(1).alignment = { vertical: 'middle' };

    // Vta monthly cells
    item.meses.forEach((mes, i) => {
      const cell = row.getCell(COL_VTA_MES(i));
      cell.numFmt = '#,##0';
      applyMesStyle(cell, mes, i === lastMesIdx);
    });

    // Rot monthly cells (same color, different format)
    item.meses.forEach((mes, i) => {
      const cell = row.getCell(COL_ROT_MES(i));
      cell.numFmt = '0.0000';
      applyMesStyle(cell, mes, i === lastMesIdx);
    });

    // Summary cells
    applySummaryStyle(row.getCell(COL_VTA),  '#,##0');
    applySummaryStyle(row.getCell(COL_RD),   '0.0000');
    applySummaryStyle(row.getCell(COL_DD),   '0.0000');
    applySummaryStyle(row.getCell(COL_ROTS), '0.0000');
    applySummaryStyle(row.getCell(COL_FIAB), '0.0"%"');
    applySummaryStyle(row.getCell(COL_QBK),  '0');
  }

  // ── Download ───────────────────────────────────────────────────────────────
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
