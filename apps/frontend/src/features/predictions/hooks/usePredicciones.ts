import { useQuery } from '@tanstack/react-query';
import { fetchUltimasPredicciones, searchPredicciones, fetchPrediccionesByJob } from '../utils/api';
import type { Prediccion, PrediccionPagedResponse, PrediccionSearchParams } from '../types/predicciones';

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

export function usePrediccionesByJob(jobId: number | null | undefined) {
  return useQuery<Prediccion[], Error>({
    queryKey: ['predicciones', 'byJob', jobId],
    queryFn: () => fetchPrediccionesByJob(jobId as number),
    enabled: typeof jobId === 'number' && Number.isFinite(jobId),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
  });
}
