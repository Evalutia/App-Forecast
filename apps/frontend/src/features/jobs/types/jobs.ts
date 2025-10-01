export type JobEstado =
  | 'pendiente'
  | 'ejecutando'
  | 'exitoso'
  | 'fallido'
  | 'cancelado'
  | string; 

export interface JobsQuery {
  page: number;        
  pageSize: number;    
  tipo?: string;       
  estado?: string;    
  desde?: string;      
  hasta?: string;      
}

export interface PagedResult<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

export interface JobItem {
  id: number;                 
  tipoJob: string;
  estado: JobEstado;
  fechaInicio: string;        
  fechaFin?: string | null;   
}

export interface JobDetail extends JobItem {
  detalle?: string | null;
}

export type JobsListResponse = PagedResult<JobItem>;

export type JobDetailResponse = JobDetail;

export interface PrediccionFromJob {
  id: number;                 
  sku: string;
  fechaPredicha: string;      
  cantidadPredicha: number;   
  modelo: string;
  horizonte: number;
  rmse?: number | null;      
  r2?: number | null;         
}
export type JobPrediccionesResponse = PrediccionFromJob[];
