namespace WebApi.Models
{
  public sealed class VentaAgregada
  {
    public string Periodo { get; set; } = string.Empty;
    public string Sku { get; set; } = string.Empty;
    public long TotalCantidad { get; set; }
  }
}
