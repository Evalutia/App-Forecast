using WebApi.Models;

namespace Services.Ventas
{
  public interface IVentasService
  {
    // Operaciones básicas con validaciones
    (IReadOnlyList<VentaHistorica> Items, int Total) Search(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        int page,
        int pageSize
    );

    (IReadOnlyList<VentaAgregada> Items, int Total) Aggregate(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        string periodo,
        int page,
        int pageSize
    );

    IReadOnlyList<string> DistinctSkus(string? filtro);

    // Métodos con lógica de negocio compleja
    IReadOnlyList<(string Sku, ulong TotalCantidad, double PorcentajeVentas, int? PronosticoProximoTrimestre)> TopSkusByVentas(DateOnly fechaDesde, DateOnly fechaHasta, int take);

    VentaSkuResumen GetSkuResumen(string sku, DateOnly today);
  }
}
