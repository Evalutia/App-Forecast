using WebApi.Models;

namespace Services.Ventas
{
  public interface IVentasService
  {
    (IReadOnlyList<VentaHistorica> Items, int Total) Search(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        int page,
        int pageSize
    );

    (IReadOnlyList<object> Items, int Total) Aggregate(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        string periodo,
        int page,
        int pageSize
    );

    IReadOnlyList<string> DistinctSkus(string? filtro);
  }
}
