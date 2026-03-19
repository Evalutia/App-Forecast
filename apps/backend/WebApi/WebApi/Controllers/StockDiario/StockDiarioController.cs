using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using System.Linq;
using DataAccess.Repositories.StockDiarioDataAccess;
using WebApi.Controllers.StockDiario.DTOs;

namespace WebApi.Controllers.StockDiarioApi
{
  [ApiController]
  [Route("api/[controller]")]
  [Authorize]
  public class StockDiarioController : ControllerBase
  {
    private readonly IStockDiarioRepository _repo;

    public StockDiarioController(IStockDiarioRepository repo)
    {
      _repo = repo;
    }

    [HttpPost("batch")]
    public IActionResult InsertarBatch([FromBody] List<StockDiarioDto> payload)
    {
      if (payload == null || payload.Count == 0)
        return BadRequest("El payload está vacío.");

      var registros = new List<WebApi.Models.StockDiario>(payload.Count);

      foreach (var item in payload)
      {
        if (string.IsNullOrWhiteSpace(item.Sku))
          return BadRequest("Cada registro debe tener un SKU.");

        if (!DateOnly.TryParse(item.Fecha, out var fecha))
          return BadRequest($"Fecha inválida para SKU {item.Sku}. Formato esperado: YYYY-MM-DD");

        registros.Add(new WebApi.Models.StockDiario
        {
          Sku = item.Sku,
          Fecha = fecha,
          Cantidad = item.Cantidad,
          DepositoId = item.DepositoId,
          Fuente = item.Fuente,
          TsCarga = DateTime.UtcNow
        });
      }

      _repo.InsertBatch(registros);

      return Ok(new { insertados = registros.Count });
    }

    [HttpGet]
    public IActionResult Get([FromQuery] string? sku, [FromQuery] int? year, [FromQuery] int? month, [FromQuery] int page = 1, [FromQuery] int pageSize = 50)
    {
      if (string.IsNullOrWhiteSpace(sku) || !year.HasValue || !month.HasValue)
        return BadRequest("Los parámetros 'sku', 'year' y 'month' son requeridos.");

      sku = sku!.Trim().ToUpperInvariant();

      var daily = _repo.GetDailySumBySkuAndMonth(sku, year.Value, month.Value).ToList();
      var total = daily.Count;

      var items = daily
        .OrderBy(d => d.Fecha)
        .Skip((page - 1) * pageSize)
        .Take(pageSize)
        .Select(d => new { fecha = d.Fecha.ToString("yyyy-MM-dd"), cantidad = d.CantidadTotal })
        .ToList();

      return Ok(new { items, page, pageSize, total });
    }

    [HttpGet("raw")]
    public IActionResult GetRaw([FromQuery] string? sku, [FromQuery] int? year, [FromQuery] int? month, [FromQuery] int page = 1, [FromQuery] int pageSize = 50)
    {
      var rows = _repo.Search(sku, year, month, page, pageSize, out var total);

      var outItems = rows.Select(r => new StockDiarioOutDto
      {
        Id = r.Id,
        Sku = r.Sku,
        Fecha = r.Fecha.ToString("yyyy-MM-dd"),
        Cantidad = r.Cantidad,
        DepositoId = r.DepositoId
      }).ToList();

      return Ok(new { items = outItems, page, pageSize, total });
    }
  }
}
