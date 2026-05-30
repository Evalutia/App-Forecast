import api from '../../../api/client';
import type { PlanillaFiltrosDto, PlanillaVentasPagedResponse, PlanillaVentasParams } from '../types/planilla';

const BASE = '/api/planilla';

export async function fetchPlanillaVentas(params: PlanillaVentasParams): Promise<PlanillaVentasPagedResponse> {
  const qp: Record<string, string | number> = {
    page: params.page,
    pageSize: params.pageSize,
  };
  if (params.marcaId != null) qp.marcaId = params.marcaId;
  if (params.generoId != null) qp.generoId = params.generoId;
  if (params.estadoMes) qp.estadoMes = params.estadoMes;

  const { data } = await api.get<PlanillaVentasPagedResponse>(`${BASE}/ventas`, { params: qp });
  return data;
}

export async function fetchPlanillaFiltros(): Promise<PlanillaFiltrosDto> {
  const { data } = await api.get<PlanillaFiltrosDto>(`${BASE}/filtros`);
  return data;
}
