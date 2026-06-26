using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Services.Planilla;
using WebApi.Controllers.Planilla.DTOs;

namespace WebApi.Controllers.Planilla
{
  [ApiController]
  [Route("api/[controller]")]
  [Authorize]
  public class PlanillaController : ControllerBase
  {
    private readonly IPlanillaService _planillaService;

    public PlanillaController(IPlanillaService planillaService)
    {
      _planillaService = planillaService;
    }

    [HttpGet("ventas")]
    public ActionResult<PagedResultDto<PlanillaVentasOutDto>> GetVentas(
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 50,
        [FromQuery] uint? marcaId = null,
        [FromQuery] uint? generoId = null,
        [FromQuery] uint? grupoId = null,
        [FromQuery] string? estadoMes = null)
    {
      var (items, totalSkus) = _planillaService.GetVentas(page, pageSize, marcaId, generoId, grupoId, estadoMes);
      var outItems = items.Select(i => new PlanillaVentasOutDto(i));
      return Ok(new PagedResultDto<PlanillaVentasOutDto>(outItems, page, pageSize, totalSkus));
    }

    [HttpGet("filtros")]
    public ActionResult<PlanillaFiltrosOutDto> GetFiltros([FromQuery] uint? grupoId = null)
    {
      var dto = _planillaService.GetFiltros(grupoId);
      return Ok(new PlanillaFiltrosOutDto(dto));
    }

    [HttpGet("sugerencias")]
    public ActionResult<IReadOnlyList<PlanillaSugerenciaOutDto>> GetSugerencias()
    {
      var items = _planillaService.GetSugerencias();
      return Ok(items.Select(i => new PlanillaSugerenciaOutDto(i)).ToList());
    }
  }
}
