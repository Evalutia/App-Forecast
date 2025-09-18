using Microsoft.AspNetCore.Mvc;
using Services.Predicciones;
using WebApi.Models;

namespace WebApi.Controllers.Predicciones
{
  [ApiController]
  [Route("api/[controller]")]
  public class PrediccionesController : ControllerBase
  {
    private readonly IPrediccionService _svc;
    public PrediccionesController(IPrediccionService svc)
    {
      _svc = svc;
    }

    [HttpGet("ultimas")]
    public ActionResult<IEnumerable<Prediccion>> GetUltimasBySku()
    {
      var predicciones = _svc.GetUltimasBySku();

      if (!predicciones.Any())
        return NotFound("No se encontraron predicciones para el último Job.");

      return Ok(predicciones);
    }

    [HttpGet]
    public ActionResult<object> Search(
    [FromQuery] int page = 1,
    [FromQuery] int pageSize = 50,
    [FromQuery] string? sku = null,
    [FromQuery] string? modelo = null,
    [FromQuery] DateTime? desde = null,
    [FromQuery] DateTime? hasta = null)
    {
      var (items, total) = _svc.Search(new Prediccion
      {
        Sku = sku ?? string.Empty,
        Modelo = modelo ?? string.Empty,
        FechaPredicha = desde.HasValue
              ? DateOnly.FromDateTime(desde.Value)
              : default
      });

      return Ok(new { items, page, pageSize, total });
    }

    [HttpGet("jobs/{jobId:long}")]
    public ActionResult<IEnumerable<Prediccion>> GetByJob([FromRoute] ulong jobId)
    {
      var preds = _svc.GetByJob(jobId);

      if (!preds.Any())
        return NotFound($"No se encontraron predicciones para el Job ID {jobId}.");

      return Ok(preds);
    }

  }
}
