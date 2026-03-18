import { useQuery } from '@tanstack/react-query';
import {
  fetchResumenGlobal,
  fetchStockAnalysis,
  fetchTopVentasPerdidas,
  fetchStockoutDistribution,
  fetchAbcClassification,
  fetchVentasTrend,
} from '../utils/api';
import type { StockAnalysisParams } from '../types/resultados';

export function useResumenGlobal() {
  return useQuery({
    queryKey: ['resultados', 'resumen'],
    queryFn: fetchResumenGlobal,
    staleTime: 60_000,
  });
}

export function useStockAnalysis(params: StockAnalysisParams) {
  return useQuery({
    queryKey: ['resultados', 'stock-analysis', params],
    queryFn: () => fetchStockAnalysis(params),
    staleTime: 60_000,
  });
}

export function useTopVentasPerdidas(top = 10) {
  return useQuery({
    queryKey: ['resultados', 'top-ventas-perdidas', top],
    queryFn: () => fetchTopVentasPerdidas(top),
    staleTime: 60_000,
  });
}

export function useStockoutDistribution() {
  return useQuery({
    queryKey: ['resultados', 'stockout-distribution'],
    queryFn: fetchStockoutDistribution,
    staleTime: 60_000,
  });
}

export function useAbcClassification() {
  return useQuery({
    queryKey: ['resultados', 'abc'],
    queryFn: fetchAbcClassification,
    staleTime: 60_000,
  });
}

export function useVentasTrend(meses = 12) {
  return useQuery({
    queryKey: ['resultados', 'ventas-trend', meses],
    queryFn: () => fetchVentasTrend(meses),
    staleTime: 60_000,
  });
}
