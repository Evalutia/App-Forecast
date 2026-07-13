namespace WebApi.Models
{
  public class StockResumen365
  {
    public string Sku { get; set; } = string.Empty;
    public int DiasConStock { get; set; }
    public int DiasSinStock { get; set; }
    public int TotalDias { get; set; }
    public long Ventas365 { get; set; }
    public DateTime TsCarga { get; set; }
  }
}
