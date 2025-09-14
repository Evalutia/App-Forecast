using Microsoft.AspNetCore.Mvc;
using Services.Ventas;
using WebApi.Controllers.Ventas.DTOs;
using WebApi.Models;

namespace WebApi.Controllers.Ventas
{
  [ApiController]
  [Route("api/[controller]")]
  public class VentasController : ControllerBase
  {
    private readonly IVentasService _ventasService;

    public VentasController(IVentasService ventasService)
    {
      _ventasService = ventasService;
    }

    // GET /api/ventas?sku=I0001&fechaDesde=2024-01-01&fechaHasta=2024-12-31&page=1&pageSize=50&modo=historico
    [HttpGet]
    public ActionResult<object> Get(
        [FromQuery] string? sku,
        [FromQuery] DateOnly? fechaDesde,
        [FromQuery] DateOnly? fechaHasta,
        [FromQuery] string? modo = "historico",
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 50,
        [FromQuery] string periodo = "mensual"
    )
    {
      if (modo?.ToLower() == "agregado")
      {
        var (items, total) = _ventasService.Aggregate(fechaDesde, fechaHasta, sku, periodo, page, pageSize);

        var outItems = items.Select(i =>
        {
          dynamic g = i; // anónimo desde repo
          return new VentaAgregadaOutDto(
              sku: g.Sku,
              anio: g.Anio,
              mes: (g as IDictionary<string, object>).ContainsKey("Mes") ? g.Mes : null,
              total: g.Total
          );
        });

        return Ok(new PagedResultDto<VentaAgregadaOutDto>(outItems, page, pageSize, total));
      }
      else
      {
        var (items, total) = _ventasService.Search(fechaDesde, fechaHasta, sku, page, pageSize);

        var outItems = items.Select(v => new VentaOutDto(v));

        return Ok(new PagedResultDto<VentaOutDto>(outItems, page, pageSize, total));
      }
    }

    // GET /api/ventas/distinct-skus?filtro=I00
    [HttpGet("distinct-skus")]
    public ActionResult<IEnumerable<SkuOutDto>> DistinctSkus([FromQuery] string? filtro = null)
    {
      var skus = _ventasService.DistinctSkus(filtro);
      return Ok(skus.Select(s => new SkuOutDto(s)));
    }
  }
}
