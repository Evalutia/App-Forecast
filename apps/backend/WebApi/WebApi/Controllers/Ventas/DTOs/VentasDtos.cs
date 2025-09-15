namespace WebApi.Controllers.Ventas.DTOs
{
  // DTO para ventas históricas (crudas)
  public sealed class VentaOutDto
  {
    public int Id { get; init; }
    public string Fecha { get; init; } = string.Empty;
    public string Sku { get; init; } = string.Empty;
    public int Cantidad { get; init; }
    public string Fuente { get; init; } = string.Empty;

    public VentaOutDto(int id, string fecha, string sku, int cantidad, string fuente)
    {
      Id = id;
      Fecha = fecha;
      Sku = sku;
      Cantidad = cantidad;
      Fuente = fuente;
    }
  }

  // DTO para ventas agregadas (mensual, anual o por fecha)
  public sealed class VentaAgregadaOutDto
  {
    public string Periodo { get; init; } = string.Empty; // "2025-01", "2025" o "2025-01-15"
    public string Sku { get; init; } = string.Empty;
    public uint TotalCantidad { get; init; }

    public VentaAgregadaOutDto(string periodo, string sku, uint totalCantidad)
    {
      Periodo = periodo;
      Sku = sku;
      TotalCantidad = totalCantidad;
    }
  }

  // DTO genérico de paginación
  public sealed class PagedResultDto<T>
  {
    public IEnumerable<T> Items { get; init; } = Enumerable.Empty<T>();
    public int Page { get; init; }
    public int PageSize { get; init; }
    public int Total { get; init; }

    public PagedResultDto(IEnumerable<T> items, int page, int pageSize, int total)
    {
      Items = items;
      Page = page;
      PageSize = pageSize;
      Total = total;
    }
  }
}
