using WebApi.Models;

namespace DataAccess.Repositories.PrediccionDataAccess
{
  public interface IPrediccionRepository
  {
    Prediccion? GetUltimaBySku(string sku);
    (IReadOnlyList<Prediccion> Items, int Total) Search(string? sku, string? modelo, DateTime? desde, DateTime? hasta, int page, int pageSize);
    IReadOnlyList<Prediccion> GetSeries(string sku, DateTime? desde, DateTime? hasta);
    IReadOnlyList<Prediccion> GetByJob(ulong jobId);
  }
}
