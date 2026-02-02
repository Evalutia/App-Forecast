using Microsoft.AspNetCore.Mvc;
using DataAccess.Repositories.StockDiarioDataAccess;
using WebApi.Controllers.StockDiario.DTOs;

namespace WebApi.Controllers.StockDiarioApi
{
  [ApiController]
  [Route("api/[controller]")]
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
  }
}
