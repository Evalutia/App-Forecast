namespace WebApi.Models
{
  public class PlanillaVentasCalculada
  {
    public string Sku { get; set; } = string.Empty;
    public int Year { get; set; }
    public int Month { get; set; }
    public long VentasCantidad { get; set; }
    public int DiasConStock { get; set; }
    public int DiasNaturalesMes { get; set; }
    public decimal? RotacionDiariaReal { get; set; }
    public decimal? RotacionDiariaBruta { get; set; }
    public decimal? RotacionDiariaDesestacionalizada { get; set; }
    public string EstadoMes { get; set; } = string.Empty;
    public string? FrecuenciaNivel { get; set; }
    public decimal? RotacionAjustada { get; set; }
  }
}
