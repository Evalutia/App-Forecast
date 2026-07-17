import api from '../../../api/client';
import type { UmbralesTickets, UpdateUmbralesTicketsDto } from '../types/configuracion';

const BASE = '/api/configuracion';

export async function getUmbralesTickets(): Promise<UmbralesTickets> {
  const { data } = await api.get<UmbralesTickets>(`${BASE}/umbrales-tickets`);
  return data;
}

export async function updateUmbralesTickets(body: UpdateUmbralesTicketsDto): Promise<UmbralesTickets> {
  const { data } = await api.put<UmbralesTickets>(`${BASE}/umbrales-tickets`, body);
  return data;
}
