using System.ComponentModel.DataAnnotations;

namespace WebApi.Controllers.StockDiario.DTOs
{
  public class StockDiarioDto
  {
    [Required]
    public string Sku { get; set; } = null!;

    [Required]
    [RegularExpression(@"^\d{4}-\d{2}-\d{2}$", ErrorMessage = "Fecha debe ser YYYY-MM-DD")]
    public string Fecha { get; set; } = null!;

    [Required]
    [Range(0, uint.MaxValue)]
    public uint Cantidad { get; set; }

    public string? DepositoId { get; set; }
    public string? Fuente { get; set; }
  }
}
