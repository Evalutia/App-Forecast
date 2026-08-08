import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getUmbralesTickets, updateUmbralesTickets } from '../utils/api';
import type { UmbralesTickets, UpdateUmbralesTicketsDto } from '../types/configuracion';

export const configuracionKeys = {
  umbralesTickets: ['configuracion', 'umbrales-tickets'] as const,
};

// Issue #22 establece el patrón: paginas accesibles a ambos roles que llaman
// a un endpoint admin-only deben pasar `enabled: isAdmin`, nunca tocar el
// interceptor Axios para suprimir el 403 (es una señal válida en otros
// casos). `enabled` acá replica ese patrón para el llamador (ver Leyenda en
// PlanillaTable.tsx).
export function useUmbralesTickets(enabled = true) {
  return useQuery<UmbralesTickets>({
    queryKey: configuracionKeys.umbralesTickets,
    queryFn: getUmbralesTickets,
    staleTime: 60_000,
    enabled,
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
