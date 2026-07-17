import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getUmbralesTickets, updateUmbralesTickets } from '../utils/api';
import type { UmbralesTickets, UpdateUmbralesTicketsDto } from '../types/configuracion';

export const configuracionKeys = {
  umbralesTickets: ['configuracion', 'umbrales-tickets'] as const,
};

export function useUmbralesTickets() {
  return useQuery<UmbralesTickets>({
    queryKey: configuracionKeys.umbralesTickets,
    queryFn: getUmbralesTickets,
    staleTime: 60_000,
  });
}

export function useUpdateUmbralesTickets() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateUmbralesTicketsDto) => updateUmbralesTickets(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: configuracionKeys.umbralesTickets });
    },
  });
}
