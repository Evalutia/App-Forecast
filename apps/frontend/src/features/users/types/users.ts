export type Rol = 'administrador' | 'duenoDeEmpresa' | string;

export interface UsuarioRow {
  id: number;
  correo: string;
  rol: Rol;
}

export interface PagedResult<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

export interface CrearAdministradorDto {
  correo: string;
  contrasena: string;
}

export interface CrearDuenoEmpresaDto {
  correo: string;
  contrasena: string;
}

export interface UpdateUsuarioDto {
  contrasena?: string | null;
  rol?: Rol | null;
}

// Responses de creación
export interface AdministradorOutDto {
  id: number;
  correo: string;
  rol: 'administrador';
}

export interface DuenoDeEmpresaOutDto {
  id: number;
  correo: string;
  rol: 'duenoDeEmpresa';
}
