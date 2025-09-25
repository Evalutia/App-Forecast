import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { User } from '../types/auth';
import { me } from '../../../api/auth';
import { getUser, getToken, clearAuth } from '../utils/authStorage';

export function useAuthUser(): { user: User | null; isLoading: boolean; isError: boolean } {
  const token = getToken();

  const localUser = useMemo<User | null>(() => {
    const raw = getUser();
    if (!raw) return null;
    return {
      id: (raw as any).id ?? null,
      email: (raw as any).email ?? (raw as any).correo ?? null,
      role: (raw as any).role ?? (raw as any).rol ?? null,
    };
  }, []);

  const q = useQuery({
    queryKey: ['auth', 'me', token], 
    queryFn: () => me(),            
    enabled: !!token,
    staleTime: 60_000,
    retry: false,
  });

  if (q.isError && (q.error as any)?.status === 401) {
    clearAuth();
  }

  const user = (q.data as User | undefined) ?? localUser;

  return { user, isLoading: q.isLoading && !localUser, isError: q.isError };
}
