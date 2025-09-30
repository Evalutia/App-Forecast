// src/features/ventas/hooks/useVentas.ts
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import type {
  VentasQuery,
  VentasDetalleResponse,
  VentasAgregadasResponse,
  SkusResponse,
  Venta,
  VentaAgregada,
} from "../types/ventas";
import {
  fetchVentasDetalle,
  fetchVentasAgregadas,
  fetchDistinctSkus,
} from "../utils/api";

const qk = {
  detalle: (q: VentasQuery) => [
    "ventas",
    "detalle",
    {
      fechaDesde: q.fechaDesde ?? null,
      fechaHasta: q.fechaHasta ?? null,
      sku: q.sku?.trim() || null,
      page: q.page ?? 1,
      pageSize: q.pageSize ?? 50,
    },
  ] as const,
  agregadas: (q: VentasQuery & { agregado: string }) => [
    "ventas",
    "agregadas",
    {
      agregado: q.agregado,
      fechaDesde: q.fechaDesde ?? null,
      fechaHasta: q.fechaHasta ?? null,
      sku: q.sku?.trim() || null,
      page: q.page ?? 1,
      pageSize: q.pageSize ?? 50,
    },
  ] as const,
  skus: (filtro?: string) => ["ventas", "distinct-skus", filtro?.trim() || ""] as const,
};

export const useVentasDetalle = (
  query: VentasQuery,
  options?: {
    enabled?: boolean;
    staleTime?: number;
    gcTime?: number;
  }
) => {
  const q = {
    page: 1,
    pageSize: 50,
    ...query,
  };

  return useQuery<VentasDetalleResponse, unknown, VentasDetalleResponse, ReturnType<typeof qk.detalle>>({
    queryKey: qk.detalle(q),
    queryFn: () => fetchVentasDetalle(q),
    placeholderData: keepPreviousData,
    staleTime: options?.staleTime ?? 30_000, 
    gcTime: options?.gcTime ?? 5 * 60_000, 
    enabled: options?.enabled ?? true,
  });
};

export const useVentasAgregadas = (
  query: VentasQuery & { agregado: string },
  options?: {
    enabled?: boolean;
    staleTime?: number;
    gcTime?: number;
  }
) => {
  const q = {
    page: 1,
    pageSize: 50,
    ...query,
  };

  return useQuery<VentasAgregadasResponse, unknown, VentasAgregadasResponse, ReturnType<typeof qk.agregadas>>({
    queryKey: qk.agregadas(q),
    queryFn: () => fetchVentasAgregadas(q),
    placeholderData: keepPreviousData,
    staleTime: options?.staleTime ?? 30_000,
    gcTime: options?.gcTime ?? 5 * 60_000,
    enabled: options?.enabled ?? Boolean(q.agregado),
  });
};

export const useDistinctSkus = (filtro?: string, options?: { enabled?: boolean }) => {
  return useQuery<SkusResponse>({
    queryKey: qk.skus(filtro),
    queryFn: () => fetchDistinctSkus(filtro),
    staleTime: 5 * 60_000, // 5 min
    enabled: options?.enabled ?? true,
  });
};

export const selectDetalleRows = (data?: VentasDetalleResponse): Venta[] => data?.items ?? [];
export const selectAgregadoRows = (data?: VentasAgregadasResponse): VentaAgregada[] => data?.items ?? [];

export const getTotal = (data?: VentasDetalleResponse | VentasAgregadasResponse) =>
  data?.total ?? 0;

export const getPaging = (data?: VentasDetalleResponse | VentasAgregadasResponse) => ({
  page: data?.page ?? 1,
  pageSize: data?.pageSize ?? 50,
  total: data?.total ?? 0,
});

export const ventasQueryKeys = qk;
