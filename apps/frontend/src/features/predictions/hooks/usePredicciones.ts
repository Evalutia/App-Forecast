import { useQuery } from '@tanstack/react-query';
import { fetchUltimasPredicciones, searchPredicciones, fetchTopSkusVentas, fetchVentaSkuResumen } from '../utils/api';
import type {
  Prediccion,
  PrediccionPagedResponse,
  PrediccionSearchParams,
  TopSkuVentasRow,
  VentaSkuResumen,
} from '../types/predicciones';

export function useUltimasPredicciones() {
  return useQuery<Prediccion[], Error>({
    queryKey: ['predicciones', 'ultimas'],
    queryFn: fetchUltimasPredicciones,
    staleTime: 30_000,
    gcTime: 5 * 60_000,
  });
}

export function usePrediccionesSearch(params: PrediccionSearchParams) {
  return useQuery<PrediccionPagedResponse, Error>({
    queryKey: ['predicciones', 'search', params],
    queryFn: () => searchPredicciones(params),
    staleTime: 15_000,
    gcTime: 5 * 60_000,
  });
}

export function useTopSkusVentas(take = 20) {
  return useQuery<TopSkuVentasRow[], Error>({
    queryKey: ['ventas', 'top-skus', take],
    queryFn: () => fetchTopSkusVentas(take),
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
  });
}

export function useVentaSkuResumen(sku: string | undefined) {
  return useQuery<VentaSkuResumen, Error>({
    queryKey: ['ventas', 'sku-resumen', sku ?? null],
    queryFn: () => fetchVentaSkuResumen(sku as string),
    enabled: Boolean(sku && sku.trim().length),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
  });
}
