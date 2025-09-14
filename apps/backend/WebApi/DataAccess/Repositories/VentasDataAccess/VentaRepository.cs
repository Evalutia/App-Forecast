using WebApi.Data;
using WebApi.Models;

namespace DataAccess.Repositories.VentaDataAccess
{
  public class VentaRepository : IVentaRepository
  {
    private readonly EvalutiaDbContext _db;
    public VentaRepository(EvalutiaDbContext db) { _db = db; }

    // Histórico de ventas con filtros + paginación
    public (IReadOnlyList<VentaHistorica> Items, int Total) Search(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        int page,
        int pageSize
    )
    {
      var q = _db.VentasHistoricas.AsQueryable();

      if (fechaDesde.HasValue) q = q.Where(v => v.Fecha >= fechaDesde.Value);
      if (fechaHasta.HasValue) q = q.Where(v => v.Fecha <= fechaHasta.Value);
      if (!string.IsNullOrWhiteSpace(sku)) q = q.Where(v => v.Sku == sku);

      var total = q.Count();
      var items = q.OrderBy(v => v.Fecha)
                   .Skip((page - 1) * pageSize)
                   .Take(pageSize)
                   .ToList();

      return (items, total);
    }

    // Ventas agregadas (ej. sumadas por mes o año)
    public (IReadOnlyList<object> Items, int Total) Aggregate(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        string periodo,
        int page,
        int pageSize
    )
    {
      var q = _db.VentasHistoricas.AsQueryable();

      if (fechaDesde.HasValue) q = q.Where(v => v.Fecha >= fechaDesde.Value);
      if (fechaHasta.HasValue) q = q.Where(v => v.Fecha <= fechaHasta.Value);
      if (!string.IsNullOrWhiteSpace(sku)) q = q.Where(v => v.Sku == sku);

      // agrupación simple por periodo
      var grouped = periodo.ToLower() switch
      {
        "mensual" => q.GroupBy(v => new { v.Sku, Mes = v.Fecha.Month, Anio = v.Fecha.Year })
                      .Select(g => new {
                        g.Key.Sku,
                        g.Key.Anio,
                        g.Key.Mes,
                        Total = g.Sum(x => (int)x.Cantidad)
                      }),
        "anual" => q.GroupBy(v => new { v.Sku, v.Fecha.Year })
                    .Select(g => new {
                      g.Key.Sku,
                      Anio = g.Key.Year,
                      Total = g.Sum(x => (int)x.Cantidad)
                    }),
        _ => q.GroupBy(v => new { v.Sku, v.Fecha })
              .Select(g => new {
                g.Key.Sku,
                g.Key.Fecha,
                Total = g.Sum(x => (int)x.Cantidad)
              })
      };

      var total = grouped.Count();
      var items = grouped
                  .OrderBy(g => g.Sku)
                  .Skip((page - 1) * pageSize)
                  .Take(pageSize)
                  .ToList<object>();

      return (items, total);
    }

    // Lista de SKUs distintos
    public IReadOnlyList<string> DistinctSkus(string? filtro)
    {
      var q = _db.VentasHistoricas.Select(v => v.Sku).Distinct();

      if (!string.IsNullOrWhiteSpace(filtro))
        q = q.Where(s => s.Contains(filtro));

      return q.OrderBy(s => s).ToList();
    }
  }
}
