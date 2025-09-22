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

    [HttpGet]
    public ActionResult<PagedResultDto<object>> Get(
    [FromQuery] DateTime? fechaDesde,
    [FromQuery] DateTime? fechaHasta,
    [FromQuery] string? sku,
    [FromQuery] int page = 1,
    [FromQuery] int pageSize = 50,
    [FromQuery] string? agregado = null)
    {
      DateOnly? desde = fechaDesde.HasValue ? DateOnly.FromDateTime(fechaDesde.Value.Date) : (DateOnly?)null;
      DateOnly? hasta = fechaHasta.HasValue ? DateOnly.FromDateTime(fechaHasta.Value.Date) : (DateOnly?)null;

      if (!string.IsNullOrWhiteSpace(agregado))
      {
        var (items, total) = _ventasService.Aggregate(desde, hasta, sku, agregado, page, pageSize);
        var outItems = items.Select(v => new VentaAgregadaOutDto(v.Periodo, v.Sku, v.TotalCantidad));
        return Ok(new PagedResultDto<VentaAgregadaOutDto>(outItems, page, pageSize, total));
      }
      else
      {
        var (items, total) = _ventasService.Search(desde, hasta, sku, page, pageSize);
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


    [HttpGet("distinct-skus")]
    public ActionResult<IReadOnlyList<string>> DistinctSkus([FromQuery] string? filtro = null)
    {
      SkusQueryValidator.ValidarFiltro(filtro);

      var skus = _ventasService.DistinctSkus(filtro);
      return Ok(skus);
    }
  }
}
