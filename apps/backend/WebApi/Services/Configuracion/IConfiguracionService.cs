namespace Services.Configuracion
{
  public interface IConfiguracionService
  {
    (int TicketsBajoMax, int TicketsAltoMin) GetUmbralesTickets();
    void ActualizarUmbralesTickets(int ticketsBajoMax, int ticketsAltoMin, ulong? actualizadoPor);
  }
}
