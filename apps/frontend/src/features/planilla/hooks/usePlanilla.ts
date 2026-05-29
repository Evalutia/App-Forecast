import { useQuery } from '@tanstack/react-query';
import { fetchPlanillaFiltros, fetchPlanillaVentas } from '../utils/api';
import type { PlanillaFiltrosDto, PlanillaVentasPagedResponse, PlanillaVentasParams } from '../types/planilla';

export function usePlanillaVentas(params: PlanillaVentasParams) {
  return useQuery<PlanillaVentasPagedResponse, Error>({
    queryKey: ['planilla', 'ventas', params],
    queryFn: () => fetchPlanillaVentas(params),
    staleTime: 60_000,
    gcTime: 5 * 60_000,
  });
}

export function usePlanillaFiltros() {
  return useQuery<PlanillaFiltrosDto, Error>({
    queryKey: ['planilla', 'filtros'],
    queryFn: fetchPlanillaFiltros,
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
  });
}
