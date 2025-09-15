using Microsoft.AspNetCore.Mvc;
using Services.Ventas;
using WebApi.Controllers.Ventas.DTOs;
using Models.Validators;

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

    // GET /api/ventas → histórico o agregado
    [HttpGet]
    public ActionResult<PagedResultDto<object>> Get(
        [FromQuery] DateOnly? fechaDesde,
        [FromQuery] DateOnly? fechaHasta,
        [FromQuery] string? sku,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 50,
        [FromQuery] string? agregado = null)
    {
      // ✅ Validación de parámetros
      VentasQueryValidator.ValidarParametros(fechaDesde, fechaHasta, sku,
          string.IsNullOrEmpty(agregado) ? "historico" : "agregado");

      if (!string.IsNullOrWhiteSpace(agregado))
      {
        var (items, total) = _ventasService.Aggregate(fechaDesde, fechaHasta, sku, agregado, page, pageSize);
        var outItems = items.Select(v => new VentaAgregadaOutDto(v.Periodo, v.Sku, v.TotalCantidad));
        return Ok(new PagedResultDto<VentaAgregadaOutDto>(outItems, page, pageSize, total));
      }
      else
      {
        var (items, total) = _ventasService.Search(fechaDesde, fechaHasta, sku, page, pageSize);
        var outItems = items.Select(v => new VentaOutDto(
            id: (int)v.Id,
            fecha: v.Fecha.ToString("yyyy-MM-dd"),
            sku: v.Sku,
            cantidad: (int)v.Cantidad,
            fuente: v.Fuente ?? string.Empty
        ));
        return Ok(new PagedResultDto<VentaOutDto>(outItems, page, pageSize, total));
      }
    }

    // GET /api/ventas/distinct-skus → autocompletar
    [HttpGet("distinct-skus")]
    public ActionResult<IReadOnlyList<string>> DistinctSkus([FromQuery] string? filtro = null)
    {
      // ✅ Validación del filtro
      SkusQueryValidator.ValidarFiltro(filtro);

      var skus = _ventasService.DistinctSkus(filtro);
      return Ok(skus);
    }
  }
}
