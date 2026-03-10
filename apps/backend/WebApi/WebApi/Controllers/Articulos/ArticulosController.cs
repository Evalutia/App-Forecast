using Microsoft.AspNetCore.Mvc;
using DataAccess.Repositories.ArticuloDataAccess;
using WebApi.Models;
using WebApi.Controllers.Articulos.DTOs;

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
      [FromQuery] string? sku,
      [FromQuery] string? familiaNombre,
      [FromQuery] string? generoDescripcion,
      [FromQuery] int page = 1,
      [FromQuery] int pageSize = 100)
    {
      var (items, total) = _repo.Search(sku, familiaNombre, generoDescripcion, page, pageSize);
      return Ok(new { items, page, pageSize, total });
    }

    [HttpGet("distinct-familias")]
    public IActionResult DistinctFamilias()
    {
      var familias = _repo.DistinctFamilias();
      return Ok(familias);
    }

    [HttpGet("distinct-generos")]
    public IActionResult DistinctGeneros()
    {
      var generos = _repo.DistinctGeneros();
      return Ok(generos);
    }
  }
}
