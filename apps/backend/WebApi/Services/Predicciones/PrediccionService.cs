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

    public IReadOnlyList<Prediccion> GetUltimasBySku()
    {
      var items = _repo.GetUltimasBySku()?.ToList() ?? new List<Prediccion>();

      if (items.Count == 0)
        throw new KeyNotFoundException("No se encontraron predicciones para el último Job.");

      return items;
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
