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
  frecuenciaNivel: 'alta' | 'media' | 'baja' | null;
  rotacionAjustada: number | null;
  ticketsMes: number;
  valorHistorico: number | null;
  valorAjustado: number | null;
  criterioFrecuencia: 'historico' | 'promedio' | 'real_extrapolado' | null;
}

export interface PlanillaVentasDto {
  sku: string;
  descripcion: string | null;
  codigoBarras: string | null;
  marcaNombre: string | null;
  generoDescripcion: string | null;
  stockMinimo: number | null;
  estadoArticulo?: string;
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
  grupos: PlanillaFiltroItemDto[];
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
  grupoId?: number;
  estadoMes?: string;
  criterioFrecuencia?: string;
}

export interface PlanillaSugerenciaDto {
  sku: string;
  rotacionSugerida: number | null;
  fiabilidadPorcentaje: number | null;
  diasHastaQuiebre: number | null;
}
