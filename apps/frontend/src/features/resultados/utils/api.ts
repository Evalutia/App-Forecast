import api from '../../../api/client';
import type {
  ResumenGlobal,
  StockAnalysisPagedResponse,
  StockAnalysisParams,
  TopVentasPerdidas,
  StockoutDistribution,
  AbcSummary,
  VentasMensualesTrend,
} from '../types/resultados';

const BASE = '/api/resultados';

export async function fetchResumenGlobal() {
  const { data } = await api.get<ResumenGlobal>(`${BASE}/resumen`);
  return data;
}

export async function fetchStockAnalysis(params: StockAnalysisParams = {}) {
  const qp: Record<string, string | number> = {};
  if (params.sku) qp.sku = params.sku;
  if (params.orderBy) qp.orderBy = params.orderBy;
  if (typeof params.page === 'number') qp.page = params.page;
  if (typeof params.pageSize === 'number') qp.pageSize = params.pageSize;

  const { data } = await api.get<StockAnalysisPagedResponse>(`${BASE}/stock-analysis`, { params: qp });
  return data;
}

export async function fetchTopVentasPerdidas(top = 10) {
  const { data } = await api.get<TopVentasPerdidas[]>(`${BASE}/charts/top-ventas-perdidas`, { params: { top } });
  return data;
}

export async function fetchStockoutDistribution() {
  const { data } = await api.get<StockoutDistribution>(`${BASE}/charts/stockout-distribution`);
  return data;
}

export async function fetchAbcClassification() {
  const { data } = await api.get<AbcSummary>(`${BASE}/charts/abc`);
  return data;
}

export async function fetchVentasTrend(meses = 12) {
  const { data } = await api.get<VentasMensualesTrend[]>(`${BASE}/charts/ventas-trend`, { params: { meses } });
  return data;
}
