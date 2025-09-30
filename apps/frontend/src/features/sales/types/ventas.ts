export type PagedResult<T> = {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
};

export type Venta = {
  id: number;
  fecha: string;
  sku: string;
  cantidad: number;
  fuente: string; 
};

export type VentaAgregada = {
  periodo: string;
  sku: string;
  totalCantidad: number; 
};

export type VentasQuery = {
  fechaDesde?: string; 
  fechaHasta?: string; 
  sku?: string;
  page?: number;
  pageSize?: number;
  agregado?: string;
};

export type VentasDetalleResponse = PagedResult<Venta>;

export type VentasAgregadasResponse = PagedResult<VentaAgregada>;

export type SkusResponse = string[];

export const parseIsoDate = (s: string | undefined) =>
  s ? new Date(s + "T00:00:00") : undefined;

export const formatPeriodo = (p: string) => p;
