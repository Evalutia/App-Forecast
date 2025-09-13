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

    public Prediccion? GetUltima(string sku)
    {
      return _repo.GetUltimaBySku(sku);
    }

    public (IReadOnlyList<Prediccion> Items, int Total) Search(
        string? sku, string? modelo, DateTime? desde, DateTime? hasta, int page, int pageSize)
    {
      return _repo.Search(sku, modelo, desde, hasta, page, pageSize);
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
