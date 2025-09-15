namespace WebApi.Models
{
  public sealed class VentaAgregada
  {
    public string Periodo { get; set; } = string.Empty;  // Ej: "2025-01" o "2025"
    public string Sku { get; set; } = string.Empty;
    public uint TotalCantidad { get; set; }
  }
}
