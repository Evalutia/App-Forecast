using DataAccess.Repositories.ConfiguracionDataAccess;

namespace Services.Configuracion
{
  public class ConfiguracionService : IConfiguracionService
  {
    // Mismos defaults que TICKETS_BAJO_MAX/TICKETS_ALTO_MIN en
    // services/etl/run_calc_planilla.py -- si la fila no existe (no deberia
    // pasar, la migracion la siembra) no se rompe la pantalla por un dato
    // de configuracion faltante.
    private const int DefaultTicketsBajoMax = 2;
    private const int DefaultTicketsAltoMin = 5;

    private const string ClaveTicketsBajoMax = "tickets_bajo_max";
    private const string ClaveTicketsAltoMin = "tickets_alto_min";

    private readonly IConfiguracionRepository _repo;

    public ConfiguracionService(IConfiguracionRepository repo)
    {
      _repo = repo;
    }

    public (int TicketsBajoMax, int TicketsAltoMin) GetUmbralesTickets()
    {
      var claves = new[] { ClaveTicketsBajoMax, ClaveTicketsAltoMin };
      var filas = _repo.ListPorClaves(claves).ToDictionary(c => c.Clave, c => c.Valor);

      var bajo = ParseOrDefault(filas.GetValueOrDefault(ClaveTicketsBajoMax), DefaultTicketsBajoMax);
      var alto = ParseOrDefault(filas.GetValueOrDefault(ClaveTicketsAltoMin), DefaultTicketsAltoMin);
      return (bajo, alto);
    }

    public void ActualizarUmbralesTickets(int ticketsBajoMax, int ticketsAltoMin, ulong? actualizadoPor)
    {
      if (ticketsBajoMax <= 0 || ticketsAltoMin <= 0)
      {
        throw new InvalidOperationException("Los umbrales deben ser mayores a 0");
      }

      if (ticketsBajoMax >= ticketsAltoMin)
      {
        throw new InvalidOperationException("tickets_bajo_max debe ser menor que tickets_alto_min");
      }

      _repo.UpsertMuchas(
        new[]
        {
          (ClaveTicketsBajoMax, ticketsBajoMax.ToString()),
          (ClaveTicketsAltoMin, ticketsAltoMin.ToString())
        },
        actualizadoPor);
    }

    private static int ParseOrDefault(string? valor, int fallback)
    {
      return int.TryParse(valor, out var parsed) ? parsed : fallback;
    }
  }
}
