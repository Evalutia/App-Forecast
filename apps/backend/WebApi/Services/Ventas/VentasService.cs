using DataAccess.Repositories.VentaDataAccess;
using WebApi.Models;

namespace Services.Ventas
{
  public class VentasService : IVentasService
  {
    private readonly IVentaRepository _repo;

    public VentasService(IVentaRepository repo)
    {
      _repo = repo;
    }

    public (IReadOnlyList<VentaHistorica> Items, int Total) Search(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        int page,
        int pageSize)
    {
      if (page < 1)
        throw new InvalidOperationException("page debe ser >= 1");

      if (pageSize is < 1 or > 200)
        throw new InvalidOperationException("pageSize fuera de rango (1..200)");

      return _repo.Search(fechaDesde, fechaHasta, sku, page, pageSize);
    }

    public (IReadOnlyList<VentaAgregada> Items, int Total) Aggregate(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        string periodo,
        int page,
        int pageSize)
    {
      if (page < 1)
        throw new InvalidOperationException("page debe ser >= 1");

      if (pageSize is < 1 or > 200)
        throw new InvalidOperationException("pageSize fuera de rango (1..200)");

      return _repo.Aggregate(fechaDesde, fechaHasta, sku, periodo, page, pageSize);
    }

    public IReadOnlyList<string> DistinctSkus(string? filtro)
    {
      return _repo.DistinctSkus(filtro);
    }
  }
}
