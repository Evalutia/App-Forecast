using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using System.Linq;
using WebApi.Data;

namespace WebApi.Controllers.VentasMensuales
{
  [ApiController]
  [Route("api/[controller]")]
  [Authorize]
  public class VentasMensualesController : ControllerBase
  {
    private readonly EvalutiaDbContext _db;

    public VentasMensualesController(EvalutiaDbContext db)
    {
      _db = db;
    }

    [HttpGet]
    public ActionResult<WebApi.Controllers.VentasMensuales.DTOs.PagedResultDto<WebApi.Controllers.VentasMensuales.DTOs.VentasMensualesOutDto>> Get([
      FromQuery] string? sku,
      [FromQuery] int page = 1,
      [FromQuery] int pageSize = 100,
      [FromQuery] int? year = null,
      [FromQuery] int? month = null)
    {
      var q = _db.VentasMensuales.AsQueryable();

      if (!string.IsNullOrWhiteSpace(sku)) q = q.Where(x => x.Sku == sku);
      if (year.HasValue) q = q.Where(x => x.Year == year.Value);
      if (month.HasValue) q = q.Where(x => x.Month == month.Value);

      var total = q.Count();

      var outItems = q.OrderByDescending(x => x.Year)
                      .ThenByDescending(x => x.Month)
                      .ThenBy(x => x.Sku)
                      .Skip((page - 1) * pageSize)
                      .Take(pageSize)
                      .Select(x => new WebApi.Controllers.VentasMensuales.DTOs.VentasMensualesOutDto(
                        x.Id,
                        x.Sku,
                        x.Year,
                        x.Month,
                        x.VentasCantidad,
                        x.DiasConStock,
                        x.Fuente ?? string.Empty
                      ))
                      .ToList();

      return Ok(new WebApi.Controllers.VentasMensuales.DTOs.PagedResultDto<WebApi.Controllers.VentasMensuales.DTOs.VentasMensualesOutDto>(outItems, page, pageSize, total));
    }
  }
}
