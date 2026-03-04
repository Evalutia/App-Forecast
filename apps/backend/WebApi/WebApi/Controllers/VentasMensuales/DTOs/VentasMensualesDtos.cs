using System.Collections.Generic;
using System.Linq;

namespace WebApi.Controllers.VentasMensuales.DTOs
{
  public sealed class VentasMensualesOutDto
  {
    public ulong Id { get; init; }
    public string Sku { get; init; } = string.Empty;
    public int Year { get; init; }
    public int Month { get; init; }
    public ulong VentasCantidad { get; init; }
    public ushort DiasConStock { get; init; }
    public string Fuente { get; init; } = string.Empty;
    public VentasMensualesOutDto(ulong id, string sku, int year, int month, ulong ventasCantidad, ushort diasConStock, string fuente)
    {
      Id = id;
      Sku = sku;
      Year = year;
      Month = month;
      VentasCantidad = ventasCantidad;
      DiasConStock = diasConStock;
      Fuente = fuente;
    }
  }

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
