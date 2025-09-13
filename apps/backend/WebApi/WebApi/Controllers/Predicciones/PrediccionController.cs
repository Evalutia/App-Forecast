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

    [HttpGet("ultima")]
    public ActionResult<Prediccion?> GetUltima([FromQuery] string sku)
    {
      var pred = _svc.GetUltima(sku);
      if (pred == null) return NotFound();
      return Ok(pred);
    }

    [HttpGet]
    public ActionResult<object> Search(
      [FromQuery] string? sku = null,
      [FromQuery] string? modelo = null,
      [FromQuery] DateTime? desde = null,
      [FromQuery] DateTime? hasta = null,
      [FromQuery] int page = 1,
      [FromQuery] int pageSize = 50)
    {
      var (items, total) = _svc.Search(sku, modelo, desde, hasta, page, pageSize);
      return Ok(new { items, page, pageSize, total });
    }

    [HttpGet("series")]
    public ActionResult<IEnumerable<Prediccion>> Series(
      [FromQuery] string sku,
      [FromQuery] DateTime? desde = null,
      [FromQuery] DateTime? hasta = null)
    {
      var series = _svc.Series(sku, desde, hasta);
      return Ok(series);
    }

    [HttpGet("jobs/{jobId:long}")]
    public ActionResult<IEnumerable<Prediccion>> GetByJob([FromRoute] ulong jobId)
    {
      var preds = _svc.GetByJob(jobId);
      return Ok(preds);
    }
  }
}
