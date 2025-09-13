using WebApi.Data;
using WebApi.Models;

namespace DataAccess.Repositories.PrediccionDataAccess
{
  public class PrediccionRepository : IPrediccionRepository
  {
    private readonly EvalutiaDbContext _db;
    public PrediccionRepository(EvalutiaDbContext db)
    {
      _db = db;
    }

    public Prediccion? GetUltimaBySku(string sku)
    {
      return _db.Predicciones
                .Where(p => p.Sku == sku)
                .OrderByDescending(p => p.TsGeneracion)
                .FirstOrDefault();
    }

    public (IReadOnlyList<Prediccion> Items, int Total) Search(
        string? sku, string? modelo, DateTime? desde, DateTime? hasta, int page, int pageSize)
    {
      var q = _db.Predicciones.AsQueryable();

      if (!string.IsNullOrWhiteSpace(sku)) q = q.Where(p => p.Sku == sku);
      if (!string.IsNullOrWhiteSpace(modelo)) q = q.Where(p => p.Modelo == modelo);
      if (desde.HasValue) q = q.Where(p => p.FechaPredicha >= DateOnly.FromDateTime(desde.Value));
      if (hasta.HasValue) q = q.Where(p => p.FechaPredicha <= DateOnly.FromDateTime(hasta.Value));

      var total = q.Count();
      var items = q.OrderByDescending(p => p.FechaPredicha)
                   .Skip((page - 1) * pageSize)
                   .Take(pageSize)
                   .ToList();

      return (items, total);
    }

    public IReadOnlyList<Prediccion> GetSeries(string sku, DateTime? desde, DateTime? hasta)
    {
      var q = _db.Predicciones.Where(p => p.Sku == sku);

      if (desde.HasValue) q = q.Where(p => p.FechaPredicha >= DateOnly.FromDateTime(desde.Value));
      if (hasta.HasValue) q = q.Where(p => p.FechaPredicha <= DateOnly.FromDateTime(hasta.Value));

      return q.OrderBy(p => p.FechaPredicha).ToList();
    }

    public IReadOnlyList<Prediccion> GetByJob(ulong jobId)
    {
      return _db.Predicciones.Where(p => p.JobId == jobId)
                             .OrderBy(p => p.FechaPredicha)
                             .ToList();
    }
  }
}
