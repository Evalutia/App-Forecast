using WebApi.Models;

namespace Services.Predicciones
{
  public interface IPrediccionService
  {
    Prediccion? GetUltima(string sku);
    (IReadOnlyList<Prediccion> Items, int Total) Search(string? sku, string? modelo, DateTime? desde, DateTime? hasta, int page, int pageSize);
    IReadOnlyList<Prediccion> Series(string sku, DateTime? desde, DateTime? hasta);
    IReadOnlyList<Prediccion> GetByJob(ulong jobId);
  }
}
