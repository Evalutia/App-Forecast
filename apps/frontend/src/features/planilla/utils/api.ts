import api from '../../../api/client';
import type { PlanillaFiltrosDto, PlanillaSugerenciaDto, PlanillaVentasPagedResponse, PlanillaVentasParams } from '../types/planilla';

const BASE = '/api/planilla';

export async function fetchPlanillaVentas(params: PlanillaVentasParams): Promise<PlanillaVentasPagedResponse> {
  const qp: Record<string, string | number> = {
    page: params.page,
    pageSize: params.pageSize,
  };
  if (params.marcaId != null) qp.marcaId = params.marcaId;
  if (params.generoId != null) qp.generoId = params.generoId;
  if (params.grupoId != null) qp.grupoId = params.grupoId;
  if (params.estadoMes) qp.estadoMes = params.estadoMes;

  const { data } = await api.get<PlanillaVentasPagedResponse>(`${BASE}/ventas`, { params: qp });
  return data;
}

export async function fetchPlanillaFiltros(grupoId?: number): Promise<PlanillaFiltrosDto> {
  const qp: Record<string, number> = {};
  if (grupoId != null) qp.grupoId = grupoId;

  const { data } = await api.get<PlanillaFiltrosDto>(`${BASE}/filtros`, { params: qp });
  return data;
}

export async function fetchPlanillaSugerencias(): Promise<PlanillaSugerenciaDto[]> {
  const { data } = await api.get<PlanillaSugerenciaDto[]>(`${BASE}/sugerencias`);
  return data;
}
