import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listUsuarios,
  getUsuario,
  updateUsuario,
  crearAdministrador,
  crearDuenoEmpresa,
  borrarAdministradorPorCorreo,
} from '../utils/api';
import type {
  UsuarioRow,
  PagedResult,
  CrearAdministradorDto,
  CrearDuenoEmpresaDto,
  UpdateUsuarioDto,
} from '../types/users';

export const usersKeys = {
  all: ['users'] as const,
  list: (q: { page?: number; pageSize?: number; correo?: string; rol?: string }) =>
    [...usersKeys.all, 'list', q] as const,
  byId: (id: number) => [...usersKeys.all, 'byId', id] as const,
};

export function useUsuariosList(q: { page?: number; pageSize?: number; correo?: string; rol?: string }) {
  return useQuery<PagedResult<UsuarioRow>>({
    queryKey: usersKeys.list(q),
    queryFn: () => listUsuarios(q),
    placeholderData: undefined,
    staleTime: 60_000,
  });
}

export function useUsuario(id: number) {
  return useQuery<UsuarioRow>({
    queryKey: usersKeys.byId(id),
    queryFn: () => getUsuario(id),
    enabled: !!id,
    staleTime: 60_000,
  });
}

export function useUpdateUsuario() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: { id: number; body: UpdateUsuarioDto }) => updateUsuario(p.id, p.body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: usersKeys.byId(vars.id) });
      qc.invalidateQueries({ queryKey: usersKeys.all });
    },
  });
}

export function useCrearAdministrador() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CrearAdministradorDto) => crearAdministrador(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: usersKeys.all });
    },
  });
}

export function useCrearDuenoEmpresa() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CrearDuenoEmpresaDto) => crearDuenoEmpresa(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: usersKeys.all });
    },
  });
}

export function useBorrarAdministradorPorCorreo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (correo: string) => borrarAdministradorPorCorreo(correo),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: usersKeys.all });
    },
  });
}
