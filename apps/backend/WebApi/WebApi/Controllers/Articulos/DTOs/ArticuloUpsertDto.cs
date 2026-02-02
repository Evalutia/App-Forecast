using System.ComponentModel.DataAnnotations;

namespace WebApi.Controllers.Articulos.DTOs
{
  public class ArticuloUpsertDto
  {
    [Required]
    public string Sku { get; set; } = null!;

    [Required]
    public string Barcode { get; set; } = null!;

    [Required]
    public string Descripcion { get; set; } = null!;

    [Required]
    public uint FamiliaId { get; set; }

    [Required]
    public string FamiliaNombre { get; set; } = null!;

    [Required]
    public uint GeneroId { get; set; }

    [Required]
    public string GeneroDescripcion { get; set; } = null!;

    [Required]
    [Range(0, uint.MaxValue)]
    public uint StockMinimo { get; set; }

    public byte? FrecuenciaMensual { get; set; }
    public string? Fuente { get; set; }
  }
}
