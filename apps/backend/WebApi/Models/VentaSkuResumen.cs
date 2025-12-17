namespace WebApi.Models
{
  public sealed class VentaSkuResumen
  {
    public string Sku { get; set; } = string.Empty;
    public DateOnly? FechaPrimerObservacion { get; set; }
    public DateOnly? FechaUltimaObservacion { get; set; }
    public int CantidadObservaciones { get; set; }

    public ulong MinimoVentasTrimestral { get; set; }
    public string? TrimestreMinimoVentas { get; set; }

    public ulong MaximoVentasTrimestral { get; set; }
    public string? TrimestreMaximoVentas { get; set; }

    public double PromedioVentasTrimestral { get; set; }

    public ulong VentasUltimoTrimestre { get; set; }
    public string? UltimoTrimestre { get; set; }

    public ulong VentasUltimoAnioCalendario { get; set; }
    public double? CrecimientoVentasUltimoAnio { get; set; }
    public double? CrecimientoVentasUltimoTrimestreVsMismoTrimestreAnioAnterior { get; set; }

    public double? IncidenciaVentasUltimoAnioPorcentaje { get; set; }
    public double? IncidenciaVentasUltimoTrimestrePorcentaje { get; set; }

    public int? RankingUltimoAnio { get; set; }
    public int TotalSkusUltimoAnio { get; set; }
  }
}
