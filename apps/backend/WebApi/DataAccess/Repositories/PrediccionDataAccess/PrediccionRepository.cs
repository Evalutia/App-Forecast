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

    public IEnumerable<Prediccion> GetUltimasBySku()
    {
      var ultimoJobId = _db.JobsHistoriales
                           .OrderByDescending(j => j.Id)
                           .Select(j => j.Id)
                           .FirstOrDefault();

      if (ultimoJobId == 0)
        return Enumerable.Empty<Prediccion>();

      return _db.Predicciones
                .Where(p => p.JobId == ultimoJobId)
                .OrderBy(p => p.Sku)
                .ToList();
    }

    public (IReadOnlyList<Prediccion> Items, int Total) Search(
        string? sku, string? modelo, DateTime? desde, DateTime? hasta, int page, int pageSize)
    {
      var q = _db.Predicciones.AsQueryable();

      if (!string.IsNullOrWhiteSpace(sku)) q = q.Where(p => p.Sku.ToLower().StartsWith(sku.ToLower()));
      if (!string.IsNullOrWhiteSpace(modelo)) q = q.Where(p => p.Modelo.ToLower() == modelo.ToLower());
      if (desde.HasValue) q = q.Where(p => p.FechaPredicha >= DateOnly.FromDateTime(desde.Value));
      if (hasta.HasValue) q = q.Where(p => p.FechaPredicha <= DateOnly.FromDateTime(hasta.Value));

      var total = q.Count();
      var items = q.OrderByDescending(p => p.FechaPredicha)
                   .Skip((page - 1) * pageSize)
                   .Take(pageSize)
                   .ToList();

      return (items, total);
    }

    public IReadOnlyList<Prediccion> GetByJob(ulong jobId)
    {
      return _db.Predicciones.Where(p => p.JobId == jobId)
                             .OrderBy(p => p.FechaPredicha)
                             .ToList();
    }
  }
}
