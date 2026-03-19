using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Services.Resultados;
using WebApi.Models;
using WebApi.Controllers.Ventas.DTOs;

namespace WebApi.Controllers.Resultados
{
  [ApiController]
  [Route("api/[controller]")]
  [Authorize]
  public class ResultadosController : ControllerBase
  {
    private readonly IResultadosService _svc;

    public ResultadosController(IResultadosService svc)
    {
      _svc = svc;
    }

    [HttpGet("resumen")]
    public ActionResult<ResumenGlobalDto> Resumen()
    {
      return Ok(_svc.GetResumenGlobal());
    }

    [HttpGet("stock-analysis")]
    public ActionResult<PagedResultDto<SkuStockAnalysisDto>> StockAnalysis(
      [FromQuery] string? sku,
      [FromQuery] string? orderBy,
      [FromQuery] int page = 1,
      [FromQuery] int pageSize = 50)
    {
      var items = _svc.GetStockAnalysis(sku, orderBy, page, pageSize);
      var total = _svc.CountStockAnalysis(sku);
      return Ok(new PagedResultDto<SkuStockAnalysisDto>(items, page, pageSize, total));
    }

    [HttpGet("charts/top-ventas-perdidas")]
    public ActionResult<IReadOnlyList<TopVentasPerdidasDto>> TopVentasPerdidas(
      [FromQuery] int top = 10)
    {
      return Ok(_svc.GetTopVentasPerdidas(top));
    }

    [HttpGet("charts/stockout-distribution")]
    public ActionResult<StockoutDistributionDto> StockoutDistribution()
    {
      return Ok(_svc.GetStockoutDistribution());
    }

    [HttpGet("charts/abc")]
    public ActionResult<AbcSummaryDto> AbcClassification()
    {
      return Ok(_svc.GetAbcClassification());
    }

    [HttpGet("charts/ventas-trend")]
    public ActionResult<IReadOnlyList<VentasMensualesTrendDto>> VentasTrend(
      [FromQuery] int meses = 12)
    {
      return Ok(_svc.GetVentasMensualesTrend(meses));
    }
  }
}
