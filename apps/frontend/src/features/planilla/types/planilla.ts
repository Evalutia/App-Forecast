export interface PlanillaMesDto {
  year: number;
  month: number;
  ventasCantidad: number;
  diasConStock: number;
  diasNaturalesMes: number;
  rotacionDiariaReal: number | null;
  rotacionDiariaBruta: number | null;
  rotacionDiariaDesestacionalizada: number | null;
  estadoMes: 'normal' | 'quiebre_parcial' | 'sin_stock';
}

export interface PlanillaVentasDto {
  sku: string;
  descripcion: string | null;
  marcaNombre: string | null;
  generoDescripcion: string | null;
  stockMinimo: number | null;
  meses: PlanillaMesDto[];
}

export interface PlanillaVentasPagedResponse {
  items: PlanillaVentasDto[];
  page: number;
  pageSize: number;
  total: number;
}

export interface PlanillaFiltroItemDto {
  id: number;
  nombre: string;
}

export interface PlanillaFiltrosDto {
  marcas: PlanillaFiltroItemDto[];
  generos: PlanillaFiltroItemDto[];
  articulosIncompletos: {
    sinMarca: number;
    sinGenero: number;
  };
}

export interface PlanillaVentasParams {
  page: number;
  pageSize: number;
  marcaId?: number;
  generoId?: number;
  estadoMes?: string;
}
