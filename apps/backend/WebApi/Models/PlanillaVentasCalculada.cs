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
    public byte TicketsMes { get; set; }
    public decimal? ValorHistorico { get; set; }
    public decimal? ValorAjustado { get; set; }
    public string? CriterioFrecuencia { get; set; }
    // Issue #137: "V/E" -- venta real del mes, o su extrapolacion si hubo
    // quiebre. Antes se recalculaba en el frontend (TypeScript, 3 copias de
    // la formula); ahora se persiste en la misma corrida que ValorAjustado
    // para que las dos columnas no puedan desincronizarse.
    public decimal? VentaOExtrapolacion { get; set; }
    // Issue #145: true si el stock diario paso de 0 a positivo en algun
    // punto de un mes con quiebre -- distingue "se agoto y no repuso" de
    // "se quedo sin stock y entro una importacion a mitad de mes" (pedido
    // de Rodrigo). Siempre false fuera de quiebre_parcial.
    public bool IngresoDuranteQuiebre { get; set; }
  }
}
