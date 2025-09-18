using WebApi.Models;

namespace Services.Jobs
{
  public interface IJobService
  {
    (IReadOnlyList<JobHistorial> Items, int Total) Search(JobHistorial q, int page = 1, int pageSize = 50);
    JobHistorial GetById(ulong id);
    IReadOnlyList<Prediccion> GetPredicciones(ulong jobId);
  }
}
