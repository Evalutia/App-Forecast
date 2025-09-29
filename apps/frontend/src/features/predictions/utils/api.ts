import api from '../../../api/client';
import type {
  Prediccion,
  PrediccionPagedResponse,
  PrediccionSearchParams,
} from '../types/predicciones';

const BASE = '/api/predicciones';

function buildParams(params: PrediccionSearchParams = {}) {
  const {
    sku,
    modelo,
    desde,
    hasta,
    page,
    pageSize,
  } = params;

  const qp: Record<string, string | number> = {};
  if (sku) qp.sku = sku;
  if (modelo) qp.modelo = modelo;
  if (desde) qp.desde = desde;     
  if (hasta) qp.hasta = hasta;     
  if (typeof page === 'number') qp.page = page;
  if (typeof pageSize === 'number') qp.pageSize = pageSize;

  return qp;
}

export async function fetchUltimasPredicciones() {
  const { data } = await api.get<Prediccion[]>(`${BASE}/ultimas`);
  return data;
}

export async function searchPredicciones(params: PrediccionSearchParams = {}) {
  const { data } = await api.get<PrediccionPagedResponse>(BASE, {
    params: buildParams(params),
  });
  return data;
}

export async function fetchPrediccionesByJob(jobId: number) {
  const { data } = await api.get<Prediccion[]>(`${BASE}/jobs/${jobId}`);
  return data;
}
