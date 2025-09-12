using WebApi.Data;
using WebApi.Models;

namespace DataAccess.Repositories.JobDataAccess
{
  public class JobRepository : IJobRepository
  {
    private readonly EvalutiaDbContext _db;
    public JobRepository(EvalutiaDbContext db)
    {
      _db = db;
    }

    public (IReadOnlyList<JobHistorial> Items, int Total) Search(
        int page, int pageSize, string? tipo, string? estado, DateTime? desde, DateTime? hasta)
    {
      var q = _db.JobsHistoriales.AsQueryable();

      if (!string.IsNullOrWhiteSpace(tipo)) q = q.Where(j => j.TipoJob == tipo);
      if (!string.IsNullOrWhiteSpace(estado)) q = q.Where(j => j.Estado == estado);
      if (desde.HasValue) q = q.Where(j => j.FechaInicio >= desde.Value);
      if (hasta.HasValue) q = q.Where(j => j.FechaInicio <= hasta.Value);

      var total = q.Count();
      var items = q.OrderByDescending(j => j.FechaInicio)
                   .Skip((page - 1) * pageSize)
                   .Take(pageSize)
                   .ToList();

      return (items, total);
    }

    public JobHistorial? GetById(ulong id)
    {
      return _db.JobsHistoriales.FirstOrDefault(j => j.Id == id);
    }

    public IReadOnlyList<Prediccion> GetPrediccionesByJob(ulong jobId)
    {
      return _db.Predicciones.Where(p => p.JobId == jobId).ToList();
    }
  }
}
