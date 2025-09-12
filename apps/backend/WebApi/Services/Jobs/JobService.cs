using DataAccess.Repositories.JobDataAccess;
using WebApi.Models;

namespace Services.Jobs
{
  public class JobService : IJobService
  {
    private readonly IJobRepository _repo;
    public JobService(IJobRepository repo) { _repo = repo; }

    public (IReadOnlyList<JobHistorial> Items, int Total) Search(JobHistorial q)
    {
      return _repo.Search(
        page: 1,                  
        pageSize: 50,
        tipo: q.TipoJob,
        estado: q.Estado,
        desde: q.FechaInicio == default ? null : q.FechaInicio,
        hasta: q.FechaFin
      );
    }

    public JobHistorial GetById(ulong id)
    {
      return _repo.GetById(id) ?? throw new KeyNotFoundException("Job no encontrado");
    }

    public IReadOnlyList<Prediccion> GetPredicciones(ulong jobId)
    {
      return _repo.GetPrediccionesByJob(jobId);
    }
  }
}
