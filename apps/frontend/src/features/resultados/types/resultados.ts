export interface SkuStockAnalysis {
  sku: string;
  descripcion: string | null;
  stockMinimo: number;
  ventas365: number;
  diasConStock365: number;
  diasSinStock365: number;
  ventasPorDiaConStock365: number | null;
  stockoutRate365: number;
  ventasPerdidasEstimadas365: number | null;
  pronosticoProximoTrimestre: number | null;
  sugerenciaCompra90: number | null;
}

export interface ResumenGlobal {
  totalSkus: number;
  skusConStockout: number;
  stockoutRatePromedio: number;
  ventasPerdidasTotales: number;
  r2Promedio: number;
  ultimaPrediccion: string | null;
}

export interface StockAnalysisPagedResponse {
  items: SkuStockAnalysis[];
  page: number;
  pageSize: number;
  total: number;
}

export interface StockAnalysisParams {
  sku?: string;
  orderBy?: string;
  page?: number;
  pageSize?: number;
}

// ── Chart types ────────────────────────────────────────────
export interface TopVentasPerdidas {
  sku: string;
  descripcion: string | null;
  ventasPerdidas: number;
}

export interface StockoutDistribution {
  bueno: number;
  moderado: number;
  critico: number;
  sinDatos: number;
  items: StockoutItem[];
}

export interface StockoutItem {
  sku: string;
  descripcion: string | null;
  stockoutRate: number;
  categoria: string;
}

export interface AbcItem {
  sku: string;
  descripcion: string | null;
  ventasTotal: number;
  porcentajeAcumulado: number;
  clasificacion: string;
}

export interface AbcSummary {
  cantidadA: number;
  cantidadB: number;
  cantidadC: number;
  items: AbcItem[];
}

export interface VentasMensualesTrend {
  periodo: string;
  totalUnidades: number;
  skusActivos: number;
}
