using WebApi.Models;

namespace Services.Jobs
{
  public interface IJobService
  {
    (IReadOnlyList<JobHistorial> Items, int Total) Search(JobHistorial q);
    JobHistorial GetById(ulong id);
    IReadOnlyList<Prediccion> GetPredicciones(ulong jobId);
  }
}
