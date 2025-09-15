using WebApi.Data;
using WebApi.Models;

namespace DataAccess.Repositories.VentaDataAccess
{
  public class VentaRepository : IVentaRepository
  {
    private readonly EvalutiaDbContext _db;

    public VentaRepository(EvalutiaDbContext db)
    {
      _db = db;
    }

    // Histórico: registros crudos con filtros + paginación
    public (IReadOnlyList<VentaHistorica> Items, int Total) Search(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        int page,
        int pageSize)
    {
      var q = _db.VentasHistoricas.AsQueryable();

      if (fechaDesde.HasValue)
        q = q.Where(v => v.Fecha >= fechaDesde.Value);

      if (fechaHasta.HasValue)
        q = q.Where(v => v.Fecha <= fechaHasta.Value);

      if (!string.IsNullOrWhiteSpace(sku))
        q = q.Where(v => v.Sku == sku);

      var total = q.Count();

      var items = q.OrderBy(v => v.Fecha)
                   .Skip((page - 1) * pageSize)
                   .Take(pageSize)
                   .ToList();

      return (items, total);
    }

    // Agregado: ventas agrupadas por período
    public (IReadOnlyList<VentaAgregada> Items, int Total) Aggregate(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        string periodo,
        int page,
        int pageSize)
    {
      var q = _db.VentasHistoricas.AsQueryable();

      if (fechaDesde.HasValue)
        q = q.Where(v => v.Fecha >= fechaDesde.Value);

      if (fechaHasta.HasValue)
        q = q.Where(v => v.Fecha <= fechaHasta.Value);

      if (!string.IsNullOrWhiteSpace(sku))
        q = q.Where(v => v.Sku == sku);

      // Agrupamos por período dinámicamente
      var agrupado = periodo?.ToLower() switch
      {
        "mensual" => q.GroupBy(v => new { v.Sku, v.Fecha.Year, v.Fecha.Month })
                       .Select(g => new VentaAgregada
                       {
                         Periodo = $"{g.Key.Year:D4}-{g.Key.Month:D2}",
                         Sku = g.Key.Sku,
                         TotalCantidad = (uint)g.Sum(x => x.Cantidad)
                       }),
        "anual" => q.GroupBy(v => new { v.Sku, v.Fecha.Year })
                    .Select(g => new VentaAgregada
                    {
                      Periodo = $"{g.Key.Year:D4}",
                      Sku = g.Key.Sku,
                      TotalCantidad = (uint)g.Sum(x => x.Cantidad)
                    }),
        _ => q.GroupBy(v => new { v.Sku, v.Fecha })
              .Select(g => new VentaAgregada
              {
                Periodo = g.Key.Fecha.ToString("yyyy-MM-dd"),
                Sku = g.Key.Sku,
                TotalCantidad = (uint)g.Sum(x => x.Cantidad)
              })
      };

      var total = agrupado.Count();

      var items = agrupado.OrderBy(a => a.Periodo)
                          .Skip((page - 1) * pageSize)
                          .Take(pageSize)
                          .ToList();

      return (items, total);
    }

    // Autocomplete de SKUs
    public IReadOnlyList<string> DistinctSkus(string? filtro)
    {
      var q = _db.VentasHistoricas.AsQueryable();

      if (!string.IsNullOrWhiteSpace(filtro))
        q = q.Where(v => v.Sku.Contains(filtro));

      return q.Select(v => v.Sku)
              .Distinct()
              .OrderBy(s => s)
              .Take(50) // límite para no devolver miles
              .ToList();
    }
  }
}
