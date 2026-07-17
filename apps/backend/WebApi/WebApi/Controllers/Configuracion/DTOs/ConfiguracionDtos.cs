namespace WebApi.Controllers.Configuracion.DTOs
{
  public sealed class UmbralesTicketsOutDto
  {
    public int TicketsBajoMax { get; init; }
    public int TicketsAltoMin { get; init; }
    public UmbralesTicketsOutDto(int ticketsBajoMax, int ticketsAltoMin)
    {
      TicketsBajoMax = ticketsBajoMax;
      TicketsAltoMin = ticketsAltoMin;
    }
  }

  public sealed class UpdateUmbralesTicketsDto
  {
    public int TicketsBajoMax { get; set; }
    public int TicketsAltoMin { get; set; }
  }
}
