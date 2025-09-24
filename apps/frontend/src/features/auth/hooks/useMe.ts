import { useQuery } from '@tanstack/react-query';
import { me } from '../../../api/auth';
import { getToken } from '../utils/authStorage';

export function useMe() {
  const token = getToken();
  return useQuery({
    queryKey: ['auth','me'],
    queryFn: () => me(),
    enabled: !!token, // sólo si hay token
    staleTime: 60_000,
  });
}
