using WebApi.Models;
using DataAccess.Repositories.VentaDataAccess;

namespace Services.Ventas
{
  public interface IVentasService
  {
    // Histórico crudo con filtros y paginación
    (IReadOnlyList<VentaHistorica> Items, int Total) Search(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        int page,
        int pageSize
    );

    // Ventas agregadas (mensual, anual o por fecha)
    (IReadOnlyList<VentaAgregada> Items, int Total) Aggregate(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        string periodo,
        int page,
        int pageSize
    );

    // Autocomplete SKUs
    IReadOnlyList<string> DistinctSkus(string? filtro);
  }
}
