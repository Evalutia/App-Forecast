import ExcelJS from 'exceljs';
import { fetchPlanillaVentas } from './api';
import type { PlanillaVentasDto, PlanillaVentasParams } from '../types/planilla';

const MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const mesLabel = (year: number, month: number) => `${MESES[month - 1]}/${String(year).slice(2)}`;

// Colors matching the UI
const COLOR_QUIEBRE  = 'FFCA28'; // amber
const COLOR_SINSTOCK = '90A4AE'; // slate grey
const COLOR_HEADER   = '0D5C2E'; // dark green for headers
const COLOR_SUMMARY  = '1B4332'; // darker green for summary cols

function rotDesEstac(meses: PlanillaVentasDto['meses']): number | null {
  const closed   = meses.slice(0, -1);
  const normales = closed.filter(m => m.estadoMes === 'normal' && m.rotacionDiariaReal != null);
  if (normales.length === 0) return null;
  return normales.reduce((s, m) => s + (m.rotacionDiariaReal ?? 0), 0) / normales.length;
}

function ddstk(meses: PlanillaVentasDto['meses']): number | null {
  const totalVentas = meses.reduce((s, m) => s + Number(m.ventasCantidad), 0);
  const totalDias   = meses.reduce((s, m) => s + m.diasConStock, 0);
  return totalDias === 0 ? null : totalVentas / totalDias;
}

async function fetchAll(params: PlanillaVentasParams): Promise<PlanillaVentasDto[]> {
  // Backend limits pageSize to 200 — fetch in chunks if needed
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

export async function exportPlanillaExcel(params: PlanillaVentasParams): Promise<void> {
  const items = await fetchAll(params);
  if (items.length === 0) return;

  const wb = new ExcelJS.Workbook();
  wb.creator  = 'Evalutia';
  wb.modified = new Date();

  const ws = wb.addWorksheet('Planilla de Reposición', {
    views: [{ state: 'frozen', xSplit: 1, ySplit: 1 }],
  });

  // ── Build headers ──────────────────────────────────────────────────────────
  const mesesRef = items[0].meses;
  const mesLabels = mesesRef.map(m => mesLabel(m.year, m.month));
  const lastMesIdx = mesesRef.length - 1; // reference month

  const headers = [
    'SKU',
    'Descripción',
    'Género',
    'Stock mín.',
    ...mesLabels,
    'Rot. DesEstac.',
    'DDSTK',
  ];

  // Column widths
  ws.columns = [
    { width: 13 },                        // SKU
    { width: 34 },                        // Descripción
    { width: 18 },                        // Género
    { width: 11 },                        // Stock mín.
    ...mesesRef.map((_, i) => ({          // Monthly (last one slightly different)
      width: i === lastMesIdx ? 10 : 9,
    })),
    { width: 15 },                        // Rot. DesEstac.
    { width: 12 },                        // DDSTK
  ];

  // Header row
  const headerRow = ws.addRow(headers);
  headerRow.height = 22;
  headerRow.eachCell((cell, colNum) => {
    const isSummary = colNum > 4 + mesesRef.length;
    cell.fill   = { type: 'pattern', pattern: 'solid', fgColor: { argb: `FF${isSummary ? COLOR_SUMMARY : COLOR_HEADER}` } };
    cell.font   = { bold: true, color: { argb: 'FFFFFFFF' }, size: 10 };
    cell.alignment = { vertical: 'middle', horizontal: colNum <= 2 ? 'left' : 'center', wrapText: false };
    cell.border = {
      bottom: { style: 'medium', color: { argb: 'FF34C48F' } },
    };
  });

  // ── Data rows ──────────────────────────────────────────────────────────────
  for (const item of items) {
    const rd = rotDesEstac(item.meses);
    const dd = ddstk(item.meses);

    const rowValues = [
      item.sku,
      item.descripcion ?? '',
      item.generoDescripcion ?? '',
      item.stockMinimo ?? '',
      ...item.meses.map(m => (m.rotacionDiariaReal != null ? m.rotacionDiariaReal : 0)),
      rd,
      dd,
    ];

    const row = ws.addRow(rowValues);
    row.height = 18;

    // Style fixed cols
    const skuCell = row.getCell(1);
    skuCell.font      = { bold: true, size: 10 };
    skuCell.alignment = { vertical: 'middle' };

    // Style monthly cols with estado color
    item.meses.forEach((mes, i) => {
      const col  = 5 + i;
      const cell = row.getCell(col);
      cell.numFmt    = '0.0000';
      cell.alignment = { vertical: 'middle', horizontal: 'right' };

      if (mes.estadoMes === 'quiebre_parcial') {
        cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: `FF${COLOR_QUIEBRE}` } };
        cell.font = { color: { argb: 'FF7B4A00' }, size: 10 };
      } else if (mes.estadoMes === 'sin_stock') {
        cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: `FF${COLOR_SINSTOCK}` } };
        cell.font = { color: { argb: 'FF374151' }, size: 10 };
      } else {
        // Reference month (last): subtle grey
        if (i === lastMesIdx) {
          cell.font = { color: { argb: 'FF6B7280' }, italic: true, size: 10 };
        } else {
          cell.font = { size: 10 };
        }
      }

      cell.border = {
        right: { style: 'hair', color: { argb: 'FFD1D5DB' } },
      };
    });

    // Summary cols
    const rdCell = row.getCell(5 + mesesRef.length);
    rdCell.numFmt    = '0.0000';
    rdCell.alignment = { horizontal: 'right', vertical: 'middle' };
    rdCell.font      = { bold: true, size: 10, color: { argb: 'FF065F46' } };
    rdCell.fill      = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFD1FAE5' } };

    const dCell = row.getCell(6 + mesesRef.length);
    dCell.numFmt    = '0.0000';
    dCell.alignment = { horizontal: 'right', vertical: 'middle' };
    dCell.font      = { bold: true, size: 10, color: { argb: 'FF065F46' } };
    dCell.fill      = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFD1FAE5' } };
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
