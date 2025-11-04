import * as XLSX from 'xlsx';
import { searchPredicciones } from './api';
import type { PrediccionSearchParams, Prediccion } from '../types/predicciones';

export async function exportAllPredicciones(
  filters: PrediccionSearchParams = {},
  fileName?: string
): Promise<void> {
  const pageSize = 1000;
  let page = 1;
  const all: Prediccion[] = [];
  let lastRespTotal = 0;

  while (true) {
    const resp = await searchPredicciones({ ...filters, page, pageSize });
    const items = resp?.items ?? [];
    all.push(...items);
    lastRespTotal = resp?.total ?? all.length;

    if (all.length >= lastRespTotal) break;
    page += 1;
  }

  const rows = all.map((p) => ({
    SKU: p.sku,
    Fecha: p.fechaPredicha,
    Cantidad: p.cantidadPredicha,
    Modelo: p.modelo,
    Version: p.versionModelo,
    Horizonte: p.horizonte,
    R2: p.r2 ?? '',
    RMSE: p.rmse ?? '',
    Generacion: p.tsGeneracion,
    Job: p.jobId ?? ''
  }));

  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Predicciones');

  const fname = fileName ?? `predicciones_${new Date().toISOString().slice(0, 10)}.xlsx`;
  XLSX.writeFile(wb, fname);
}
