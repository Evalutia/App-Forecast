import api from "../../../api/client"; 
import type {
  VentasQuery,
  VentasDetalleResponse,
  VentasAgregadasResponse,
  SkusResponse,
} from "../types/ventas";

const buildQuery = (q: VentasQuery = {}) => {
  const params: Record<string, string | number> = {};

  if (q.fechaDesde) params["fechaDesde"] = q.fechaDesde; 
  if (q.fechaHasta) params["fechaHasta"] = q.fechaHasta;
  if (q.sku && q.sku.trim() !== "") params["sku"] = q.sku.trim();
  if (q.page && q.page > 0) params["page"] = q.page;
  if (q.pageSize && q.pageSize > 0) params["pageSize"] = q.pageSize;
  if (q.agregado && q.agregado.trim() !== "") params["agregado"] = q.agregado.trim();

  return params;
};

export const fetchVentasDetalle = async (
  query: VentasQuery
): Promise<VentasDetalleResponse> => {
  const { agregado, ...rest } = query || {};
  const params = buildQuery(rest);

  const { data } = await api.get<VentasDetalleResponse>("/api/ventas", { params });
  return data;
};

export const fetchVentasAgregadas = async (
  query: VentasQuery & { agregado: string }
): Promise<VentasAgregadasResponse> => {
  const params = buildQuery(query);
  const { data } = await api.get<VentasAgregadasResponse>("/api/ventas", { params });
  return data;
};

export const fetchDistinctSkus = async (filtro?: string): Promise<SkusResponse> => {
  const params: Record<string, string> = {};
  if (filtro && filtro.trim() !== "") params["filtro"] = filtro.trim();

  const { data } = await api.get<SkusResponse>("/api/ventas/distinct-skus", { params });
  return data;
};
