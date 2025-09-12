using WebApi.Models;

namespace DataAccess.Repositories.JobDataAccess
{
  public interface IJobRepository
  {
    (IReadOnlyList<JobHistorial> Items, int Total) Search(
        int page, int pageSize, string? tipo, string? estado, DateTime? desde, DateTime? hasta);
    JobHistorial? GetById(ulong id);
    IReadOnlyList<Prediccion> GetPrediccionesByJob(ulong jobId);
  }

}
