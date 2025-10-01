import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  searchJobs,
  getJob,
  getJobPredicciones,
} from '../utils/api';
import type {
  JobsQuery,
  JobsListResponse,
  JobDetailResponse,
  JobPrediccionesResponse,
  JobItem,
} from '../types/jobs';

const QUERY_KEYS = {
  root: ['jobs'] as const,
  list: (q: Partial<JobsQuery>) => [...QUERY_KEYS.root, 'list', q] as const,
  detail: (id: number) => [...QUERY_KEYS.root, 'detail', id] as const,
  preds: (id: number) => [...QUERY_KEYS.root, 'preds', id] as const,
};

export function useJobs(query: Partial<JobsQuery>) {
  return useQuery<JobsListResponse>({
    queryKey: QUERY_KEYS.list(query),
    queryFn: ({ signal }) => searchJobs(query, { signal }),
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });
}

export function useJob(id?: number) {
  return useQuery<JobDetailResponse>({
    queryKey: QUERY_KEYS.detail(id ?? -1),
    queryFn: ({ signal }) => {
      if (id == null) throw new Error('id requerido');
      return getJob(id, { signal });
    },
    enabled: id != null,
    staleTime: 60_000,
  });
}

export function useJobPredicciones(id?: number) {
  return useQuery<JobPrediccionesResponse>({
    queryKey: QUERY_KEYS.preds(id ?? -1),
    queryFn: ({ signal }) => {
      if (id == null) throw new Error('id requerido');
      return getJobPredicciones(id, { signal });
    },
    enabled: id != null,
    staleTime: 60_000,
  });
}

export function usePrefetchNextJobsPage(query: Partial<JobsQuery>) {
  const qc = useQueryClient();
  return async (itemsLength?: number) => {
    const page = query.page ?? 1;
    const pageSize = query.pageSize ?? 50;
    if (itemsLength && itemsLength >= pageSize) {
      const nextQuery = { ...query, page: page + 1 };
      await qc.prefetchQuery({
        queryKey: QUERY_KEYS.list(nextQuery),
        queryFn: ({ signal }) => searchJobs(nextQuery, { signal }),
        staleTime: 30_000,
      });
    }
  };
}

export function useJobsEstadoDistrib(query: Partial<JobsQuery>) {
  const { data, isLoading, isFetching } = useJobs(query);

  const distrib = (data?.items ?? []).reduce<Record<string, number>>(
    (acc, j: JobItem) => {
      const k = j.estado || 'desconocido';
      acc[k] = (acc[k] ?? 0) + 1;
      return acc;
    },
    {}
  );

  return {
    distrib,
    total: data?.total ?? 0,
    loading: isLoading || isFetching,
  };
}
