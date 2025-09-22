using WebApi.Models;

namespace Services.Predicciones
{
  public interface IPrediccionService
  {
    IReadOnlyList<Prediccion> GetUltimasBySku();
    (IReadOnlyList<Prediccion> Items, int Total) Search(Prediccion p, int page = 1, int pageSize = 50);
    IReadOnlyList<Prediccion> GetByJob(ulong jobId);
  }
}
