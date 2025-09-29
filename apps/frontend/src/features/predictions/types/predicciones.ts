export interface JobHistorial {
  id: number;
  tipoJob: string;
  estado: string;
  fechaInicio: string;        
  fechaFin: string | null;    
  detalle: string | null;
}

export interface Prediccion {
  id: number;
  sku: string;
  fechaPredicha: string;        
  cantidadPredicha: number;
  modelo: string;
  versionModelo: string;
  horizonte: number;            
  rmse: number | null;          
  r2: number | null;            
  tsGeneracion: string;         
  jobId: number | null;
  job?: JobHistorial | null;    
}

export interface PrediccionPagedResponse {
  items: Prediccion[];
  page: number;
  pageSize: number;
  total: number;
}

export type UltimasPrediccionesResponse = Prediccion[];

export type PrediccionesByJobResponse = Prediccion[];

export interface PrediccionSearchParams {
  sku?: string;
  modelo?: string;
  desde?: string;    
  hasta?: string;    
  page?: number;
  pageSize?: number;
}
