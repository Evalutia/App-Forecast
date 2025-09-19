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

    public (IReadOnlyList<Prediccion> Items, int Total) Search(Prediccion p, int page = 1, int pageSize = 50)
    {
      return _repo.Search(
          sku: string.IsNullOrWhiteSpace(p.Sku) ? null : p.Sku,
          modelo: string.IsNullOrWhiteSpace(p.Modelo) ? null : p.Modelo,
          desde: p.FechaPredicha == default ? null : p.FechaPredicha.ToDateTime(TimeOnly.MinValue),
          hasta: p.FechaPredicha == default ? null : p.FechaPredicha.ToDateTime(TimeOnly.MaxValue),
          page: page,
          pageSize: pageSize
      );
    }


    public IReadOnlyList<Prediccion> GetByJob(ulong jobId)
    {
      var preds = _repo.GetByJob(jobId);

      if (!preds.Any())
        throw new KeyNotFoundException($"No se encontraron predicciones para el Job ID {jobId}.");

      return preds;
    }

  }
}
