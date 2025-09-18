using WebApi.Models;

namespace DataAccess.Repositories.PrediccionDataAccess
{
  public interface IPrediccionRepository
  {
    (IReadOnlyList<Prediccion> Items, int Total) Search(
      string? sku, string? modelo, DateTime? desde, DateTime? hasta, int page, int pageSize);
    IEnumerable<Prediccion> GetUltimasBySku();
    IReadOnlyList<Prediccion> GetSeries(string sku, DateTime? desde, DateTime? hasta);
    IReadOnlyList<Prediccion> GetByJob(ulong jobId);
  }
}
