// src/features/jobs/utils/api.ts
import api from '../../../api/client';
import type {
  JobsQuery,
  JobsListResponse,
  JobDetailResponse,
  JobPrediccionesResponse,
} from '../types/jobs';

const BASE = '/api/jobs';

function withDefaults(q?: Partial<JobsQuery>): JobsQuery {
  return {
    page: 1,
    pageSize: 50,
    ...q,
  };
}

function buildParams(q: JobsQuery) {
  const p: Record<string, string | number | undefined> = {
    page: q.page,
    pageSize: q.pageSize,
    tipo: q.tipo?.trim() || undefined,
    estado: q.estado?.trim() || undefined,
    desde: q.desde && q.desde.trim() !== '' ? q.desde : undefined,
    hasta: q.hasta && q.hasta.trim() !== '' ? q.hasta : undefined,
  };
  return p;
}

type FetchOpts = { signal?: AbortSignal };

export async function searchJobs(
  query?: Partial<JobsQuery>,
  opts?: FetchOpts
): Promise<JobsListResponse> {
  const q = withDefaults(query);
  const { data } = await api.get<JobsListResponse>(BASE, {
    params: buildParams(q),
    signal: opts?.signal,
  });
  return data;
}

export async function getJob(
  id: number,
  opts?: FetchOpts
): Promise<JobDetailResponse> {
  const { data } = await api.get<JobDetailResponse>(`${BASE}/${id}`, {
    signal: opts?.signal,
  });
  return data;
}

export async function getJobPredicciones(
  id: number,
  opts?: FetchOpts
): Promise<JobPrediccionesResponse> {
  const { data } = await api.get<JobPrediccionesResponse>(`${BASE}/${id}/predicciones`, {
    signal: opts?.signal,
  });
  return data;
}
