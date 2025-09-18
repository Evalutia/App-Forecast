using DataAccess.Repositories.PrediccionDataAccess;
using WebApi.Models;

namespace Services.Predicciones
{
  public class PrediccionService : IPrediccionService
  {
    private readonly IPrediccionRepository _repo;
    public PrediccionService(IPrediccionRepository repo)
    {
      _repo = repo;
    }

    public IEnumerable<Prediccion> GetUltimasBySku()
    {
      return _repo.GetUltimasBySku();
    }

    public (IReadOnlyList<Prediccion> Items, int Total) Search(Prediccion p)
    {
      return _repo.Search(
          sku: string.IsNullOrWhiteSpace(p.Sku) ? null : p.Sku,
          modelo: string.IsNullOrWhiteSpace(p.Modelo) ? null : p.Modelo,
          desde: p.FechaPredicha == default ? null : p.FechaPredicha.ToDateTime(TimeOnly.MinValue),
          hasta: p.FechaPredicha == default ? null : p.FechaPredicha.ToDateTime(TimeOnly.MaxValue),
          page: 1,
          pageSize: 50
      );
    }

    public IReadOnlyList<Prediccion> Series(string sku, DateTime? desde, DateTime? hasta)
    {
      return _repo.GetSeries(sku, desde, hasta);
    }

    public IReadOnlyList<Prediccion> GetByJob(ulong jobId)
    {
      return _repo.GetByJob(jobId);
    }
  }
}
