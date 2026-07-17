import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { User } from '../types/auth';
import { me } from '../../../api/auth';
import type { ApiError } from '../../../api/client';
import { getUser, getToken, clearAuth } from '../utils/authStorage';

/** localStorage puede tener datos guardados con el shape crudo del backend (correo/rol) de antes del refactor. */
type StoredUser = Partial<User> & { correo?: string | null; rol?: string | null };

export function useAuthUser(): { user: User | null; isLoading: boolean; isError: boolean } {
  const token = getToken();

  const localUser = useMemo<User | null>(() => {
    const raw = getUser() as StoredUser | null;
    if (!raw) return null;
    return {
      id: raw.id ?? null,
      email: raw.email ?? raw.correo ?? null,
      role: raw.role ?? raw.rol ?? null,
    };
  }, []);

  const q = useQuery({
    queryKey: ['auth', 'me', token], 
    queryFn: () => me(),            
    enabled: !!token,
    staleTime: 60_000,
    retry: false,
  });

  if (q.isError && (q.error as ApiError)?.status === 401) {
    clearAuth();
  }

  const user = (q.data as User | undefined) ?? localUser;

  return { user, isLoading: q.isLoading && !localUser, isError: q.isError };
}
