import api from './client';
import type { LoginRequest, LoginResponse, MeResponse } from '../features/auth/types/auth';

function mapLoginBody(payload: LoginRequest) {
  return { correo: payload.email, contrasena: payload.password };
}

interface RawLoginResponse {
  token?: string;
  usuario?: {
    id?: number | string | null;
    correo?: string | null;
    rol?: string | null;
  };
}

function fromRawLogin(raw: RawLoginResponse): LoginResponse {
  // backend: { token, usuario: { id, correo, rol } }
  const userRaw = raw?.usuario ?? {};
  const user = {
    id: userRaw?.id ?? null,
    email: userRaw?.correo ?? null,
    role: userRaw?.rol ?? null,
  };
  return { token: raw?.token ?? '', user };
}

export async function login(payload: LoginRequest): Promise<LoginResponse> {
  const { data } = await api.post('/api/Auth/login', mapLoginBody(payload));
  return fromRawLogin(data);
}

export async function me(): Promise<MeResponse> {
  const { data } = await api.get('/api/Auth/me');
  // data: { id, correo, rol }
  return {
    id: data?.id ?? null,
    email: data?.correo ?? null,
    role: data?.rol ?? null,
  };
}
