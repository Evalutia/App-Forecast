using WebApi.Models;

namespace Services.Predicciones
{
  public interface IPrediccionService
  {
    IEnumerable<Prediccion> GetUltimasBySku();
    (IReadOnlyList<Prediccion> Items, int Total) Search(Prediccion p);
    IReadOnlyList<Prediccion> Series(string sku, DateTime? desde, DateTime? hasta);
    IReadOnlyList<Prediccion> GetByJob(ulong jobId);
  }
}
