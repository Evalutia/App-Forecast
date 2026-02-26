using System.ComponentModel.DataAnnotations;

namespace WebApi.Controllers.Articulos.DTOs
{
  public class ArticuloUpsertDto
  {
    [Required]
    [MinLength(1)]
    public string Sku { get; set; } = null!;

    [Required]
    [MinLength(1)]
    public string Barcode { get; set; } = null!;

    [Required]
    [MinLength(1)]
    public string Descripcion { get; set; } = null!;

    [Required]
    public uint? FamiliaId { get; set; }

    [Required]
    [MinLength(1)]
    public string FamiliaNombre { get; set; } = null!;

    [Required]
    public uint? GeneroId { get; set; }

    [Required]
    [MinLength(1)]
    public string GeneroDescripcion { get; set; } = null!;

    [Required]
    [Range(0, uint.MaxValue)]
    public uint? StockMinimo { get; set; }

    public byte? FrecuenciaMensual { get; set; }
    public string? Fuente { get; set; }
  }
}
