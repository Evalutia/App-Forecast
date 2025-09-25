import api from '../../../api/client';
import type {
  UsuarioRow,
  PagedResult,
  CrearAdministradorDto,
  CrearDuenoEmpresaDto,
  AdministradorOutDto,
  DuenoDeEmpresaOutDto,
  UpdateUsuarioDto,
} from '../types/users';

const BASE = '/api/usuario';

export async function listUsuarios(params: {
  page?: number;
  pageSize?: number;
  correo?: string;
  rol?: string; // 'administrador' | 'duenoDeEmpresa'
}): Promise<PagedResult<UsuarioRow>> {
  const { data } = await api.get<PagedResult<UsuarioRow>>(BASE, { params });
  return data;
}

export async function getUsuario(id: number): Promise<UsuarioRow> {
  const { data } = await api.get<UsuarioRow>(`${BASE}/${id}`);
  return data;
}

export async function updateUsuario(id: number, body: UpdateUsuarioDto): Promise<UsuarioRow> {
  const { data } = await api.put<UsuarioRow>(`${BASE}/${id}`, body);
  return data;
}

export async function crearAdministrador(body: CrearAdministradorDto): Promise<AdministradorOutDto> {
  const { data } = await api.post<AdministradorOutDto>(`${BASE}/crear-administrador`, body);
  return data;
}

export async function crearDuenoEmpresa(body: CrearDuenoEmpresaDto): Promise<DuenoDeEmpresaOutDto> {
  const { data } = await api.post<DuenoDeEmpresaOutDto>(`${BASE}/crear-dueno-empresa`, body);
  return data;
}

export async function borrarAdministradorPorCorreo(correo: string): Promise<void> {
  await api.delete(`${BASE}/borrar-administrador/${encodeURIComponent(correo)}`);
}
