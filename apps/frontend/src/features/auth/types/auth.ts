export type Role = 'administrador' | 'duenoDeEmpresa'| string;

export interface LoginRequest {
  email: string;
  password: string;
}

export interface User {
  id: number | string | null;
  email: string | null;
  role: Role | null;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface MeResponse extends User {}
