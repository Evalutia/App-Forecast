import * as XLSX from 'xlsx';
import { fetchStockAnalysis } from './api';
import type { StockAnalysisParams, SkuStockAnalysis } from '../types/resultados';

export async function exportAllResultados(
  filters: StockAnalysisParams = {},
  fileName?: string
): Promise<void> {
  const pageSize = 1000;
  let page = 1;
  const all: SkuStockAnalysis[] = [];
  let lastRespTotal = 0;

  while (true) {
    const resp = await fetchStockAnalysis({ ...filters, page, pageSize });
    const items = resp?.items ?? [];
    all.push(...items);
    lastRespTotal = resp?.total ?? all.length;

    if (all.length >= lastRespTotal) break;
    page += 1;
  }

  const rows = all.map((r) => ({
    SKU: r.sku,
    Descripción: r.descripcion ?? '',
    'Ventas 365d': r.ventas365,
    'Días con Stock': r.diasConStock365,
    'Días sin Stock': r.diasSinStock365,
    'Stockout (%)': r.stockoutRate365,
    'Ventas perdidas est.': r.ventasPerdidasEstimadas365 ?? '',
    'Sugerencia 90d': r.sugerenciaCompra90 ?? '',
  }));

  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Resultados');

  const fname = fileName ?? `resultados_${new Date().toISOString().slice(0, 10)}.xlsx`;
  XLSX.writeFile(wb, fname);
}
