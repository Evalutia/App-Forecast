using Microsoft.AspNetCore.Mvc;
using DataAccess.Repositories.ArticuloDataAccess;
using WebApi.Controllers.Articulos.DTOs;
using WebApi.Models;

namespace WebApi.Controllers.Articulos
{
  [ApiController]
  [Route("api/[controller]")]
  public class ArticulosController : ControllerBase
  {
    private readonly IArticuloRepository _repo;

    public ArticulosController(IArticuloRepository repo)
    {
      _repo = repo;
    }

    [HttpPost("upsert")]
    public IActionResult Upsert([FromBody] ArticuloUpsertDto dto)
    {
      if (!ModelState.IsValid)
        return BadRequest(ModelState);

      var articulo = new Articulo
      {
        Sku = dto.Sku,
        Barcode = dto.Barcode,
        Descripcion = dto.Descripcion,
        FamiliaId = dto.FamiliaId,
        FamiliaNombre = dto.FamiliaNombre,
        GeneroId = dto.GeneroId,
        GeneroDescripcion = dto.GeneroDescripcion,
        StockMinimo = dto.StockMinimo,
        FrecuenciaMensual = dto.FrecuenciaMensual,
        Fuente = dto.Fuente
      };

      var guardado = _repo.Upsert(articulo);
      return Ok(guardado);
    }

    [HttpGet]
    public IActionResult Listar(
      [FromQuery] int? familiaId,
      [FromQuery] int? generoId,
      [FromQuery] int pagina = 1,
      [FromQuery] int tamanioPagina = 100)
    {
      var items = _repo.FindByFamilyOrGenre(familiaId, generoId, pagina, tamanioPagina);
      return Ok(items);
    }
  }
}
