using Microsoft.AspNetCore.Mvc;
using DataAccess.Repositories.ArticuloDataAccess;
using WebApi.Models;
using WebApi.Controllers.Articulos.DTOs;
using WebApi.Controllers.Ventas.DTOs;

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

      // Mapear DTO -> Modelo EF (teniendo en cuenta los nullable)
      var articulo = new Articulo
      {
        Sku = dto.Sku,
        Barcode = dto.Barcode,
        Descripcion = dto.Descripcion,
        FamiliaId = dto.FamiliaId,              // Articulo.FamiliaId es uint?
        FamiliaNombre = dto.FamiliaNombre,
        GeneroId = dto.GeneroId,
        GeneroDescripcion = dto.GeneroDescripcion,
        StockMinimo = dto.StockMinimo!.Value,   // Required asegura que no sea null
        FrecuenciaMensual = dto.FrecuenciaMensual,
        Fuente = dto.Fuente
      };

      var saved = _repo.Upsert(articulo);
      return Ok(saved);
    }

    [HttpGet]
    public IActionResult Listar(
      [FromQuery] int? familiaId,
      [FromQuery] int? generoId,
      [FromQuery] int pagina = 1,
      [FromQuery] int tamanioPagina = 100)
    {
      var items = _repo.FindByFamilyOrGenre(familiaId, generoId, pagina, tamanioPagina);
      var total = _repo.CountByFamilyOrGenre(familiaId, generoId);
      return Ok(new PagedResultDto<Articulo>(items, pagina, tamanioPagina, total));
    }
  }
}
