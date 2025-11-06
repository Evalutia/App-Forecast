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

      // Proyectamos siempre a un tipo anónimo consistente: Year, Month, Day, Sku, TotalCantidad
      // De esta forma la expresión tiene un único tipo y puede ser traducida por EF.
      var lowerPeriodo = periodo?.ToLower();
      var agrupado = lowerPeriodo == "mensual"
        ? q.GroupBy(v => new { v.Sku, Year = v.Fecha.Year, Month = v.Fecha.Month })
            .Select(g => new
            {
              Year = g.Key.Year,
              Month = g.Key.Month,
              Day = 1,
              Sku = g.Key.Sku,
              TotalCantidad = (uint)g.Sum(x => x.Cantidad)
            })
        : lowerPeriodo == "anual"
          ? q.GroupBy(v => new { v.Sku, Year = v.Fecha.Year })
              .Select(g => new
              {
                Year = g.Key.Year,
                Month = 0,
                Day = 0,
                Sku = g.Key.Sku,
                TotalCantidad = (uint)g.Sum(x => x.Cantidad)
              })
          : q.GroupBy(v => new { v.Sku, Fecha = v.Fecha })
              .Select(g => new
              {
                Year = g.Key.Fecha.Year,
                Month = g.Key.Fecha.Month,
                Day = g.Key.Fecha.Day,
                Sku = g.Key.Sku,
                TotalCantidad = (uint)g.Sum(x => x.Cantidad)
              });

      var total = agrupado.Count();

      // materializamos la página antes de formatear la fecha (evita llamadas a DateOnly.ToString en la traducción SQL)
      var pageItems = agrupado.OrderBy(a => a.Year)
                            .ThenBy(a => a.Month)
                            .ThenBy(a => a.Day)
                            .Skip((page - 1) * pageSize)
                            .Take(pageSize)
                            .ToList();

      // Convertir la proyección anónima a VentaAgregada formateando el periodo según 'periodo'
      List<VentaAgregada> items = pageItems.Select(x => new VentaAgregada
      {
        Periodo = lowerPeriodo == "mensual"
                    ? $"{x.Year:D4}-{x.Month:D2}"
                    : lowerPeriodo == "anual"
                      ? $"{x.Year:D4}"
                      : $"{x.Year:D4}-{x.Month:D2}-{x.Day:D2}",
        Sku = x.Sku,
        TotalCantidad = x.TotalCantidad
      }).ToList();

      return (items, total);
    }

    public IReadOnlyList<string> DistinctSkus(string? filtro)
    {
      var q = _db.VentasHistoricas.AsQueryable();

      if (!string.IsNullOrWhiteSpace(filtro))
        q = q.Where(v => v.Sku.Contains(filtro));

      return q.Select(v => v.Sku)
              .Distinct()
              .OrderBy(s => s)
              .Take(50)
              .ToList();
    }
  }
}
