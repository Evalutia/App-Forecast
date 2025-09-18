using Microsoft.AspNetCore.Mvc;
using Services.Jobs;
using WebApi.Models;

namespace WebApi.Controllers.Jobs
{
  [ApiController]
  [Route("api/[controller]")]
  public class JobsController : ControllerBase
  {
    private readonly IJobService _svc;
    public JobsController(IJobService svc) { _svc = svc; }

    [HttpGet]
    public ActionResult<object> Search(
    [FromQuery] int page = 1,
    [FromQuery] int pageSize = 50,
    [FromQuery] string? tipo = null,
    [FromQuery] string? estado = null,
    [FromQuery] DateTime? desde = null,
    [FromQuery] DateTime? hasta = null)
    {
      var (items, total) = _svc.Search(
          new JobHistorial
          {
            TipoJob = tipo ?? string.Empty,
            Estado = estado ?? string.Empty,
            FechaInicio = desde ?? default,
            FechaFin = hasta
          },
          page,
          pageSize
      );

      return Ok(new { items, page, pageSize, total });
    }


    [HttpGet("{id:long}")]
    public ActionResult<JobHistorial> GetById([FromRoute] ulong id)
    {
      var j = _svc.GetById(id);
      return Ok(j);
    }

    [HttpGet("{id:long}/predicciones")]
    public ActionResult<IEnumerable<Prediccion>> GetPredicciones([FromRoute] ulong id)
    {
      var preds = _svc.GetPredicciones(id);
      return Ok(preds);
    }
  }
}
