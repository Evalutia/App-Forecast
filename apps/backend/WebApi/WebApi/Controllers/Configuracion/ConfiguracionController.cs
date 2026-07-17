using Microsoft.AspNetCore.Mvc;
using Services.Configuracion;
using WebApi.Controllers.Configuracion.DTOs;
using WebApi.Filters;

namespace WebApi.Controllers.Configuracion
{
  [ApiController]
  [Route("api/[controller]")]
  public class ConfiguracionController : ControllerBase
  {
    private readonly IConfiguracionService _service;

    public ConfiguracionController(IConfiguracionService service)
    {
      _service = service;
    }

    [HttpGet("umbrales-tickets")]
    [AuthorizationFilter("administrador")]
    public ActionResult<UmbralesTicketsOutDto> GetUmbralesTickets()
    {
      var (bajo, alto) = _service.GetUmbralesTickets();
      return Ok(new UmbralesTicketsOutDto(bajo, alto));
    }

    [HttpPut("umbrales-tickets")]
    [AuthorizationFilter("administrador")]
    public ActionResult<UmbralesTicketsOutDto> UpdateUmbralesTickets([FromBody] UpdateUmbralesTicketsDto dto)
    {
      var idStr = User.FindFirst(System.Security.Claims.ClaimTypes.NameIdentifier)?.Value;
      ulong? actualizadoPor = ulong.TryParse(idStr, out var id) ? id : null;

      _service.ActualizarUmbralesTickets(dto.TicketsBajoMax, dto.TicketsAltoMin, actualizadoPor);

      return Ok(new UmbralesTicketsOutDto(dto.TicketsBajoMax, dto.TicketsAltoMin));
    }
  }
}
