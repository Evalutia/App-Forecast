namespace WebApi.Models
{
  public class PlanillaSugerencias
  {
    public string Sku { get; set; } = string.Empty;
    public decimal? RotacionSugerida { get; set; }
    public decimal? FiabilidadPorcentaje { get; set; }
    public decimal? DiasHastaQuiebre { get; set; }
  }
}
