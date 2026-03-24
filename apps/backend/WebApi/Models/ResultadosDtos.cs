namespace WebApi.Models
{
  public sealed class SkuStockAnalysisDto
  {
    public string Sku { get; init; } = string.Empty;
    public string? Descripcion { get; init; }
    public uint StockMinimo { get; init; }
    public int Ventas365 { get; init; }
    public int DiasConStock365 { get; init; }
    public int DiasSinStock365 { get; init; }
    public double? VentasPorDiaConStock365 { get; init; }
    public double StockoutRate365 { get; init; }
    public int? VentasPerdidasEstimadas365 { get; init; }
    public int? PronosticoProximoTrimestre { get; init; }
    public int? SugerenciaCompra90 { get; init; }
  }

  public sealed class ResumenGlobalDto
  {
    public int TotalSkus { get; init; }
    public int SkusConStockout { get; init; }
    public double StockoutRatePromedio { get; init; }
    public long VentasPerdidasTotales { get; init; }
    public double R2Promedio { get; init; }
    public string? UltimaPrediccion { get; init; }
  }

  // ── Chart DTOs ──────────────────────────────────────────────
  public sealed class TopVentasPerdidasDto
  {
    public string Sku { get; init; } = string.Empty;
    public string? Descripcion { get; init; }
    public int VentasPerdidas { get; init; }
  }

  public sealed class StockoutDistributionDto
  {
    public int Bueno { get; init; }     // <= 15%
    public int Moderado { get; init; }  // 15–30%
    public int Critico { get; init; }   // > 30%
    public int SinDatos { get; init; }  // < MIN_DIAS_STOCK
    public List<StockoutItemDto> Items { get; init; } = new();
  }

  public sealed class StockoutItemDto
  {
    public string Sku { get; init; } = string.Empty;
    public string? Descripcion { get; init; }
    public double StockoutRate { get; init; }
    public string Categoria { get; init; } = string.Empty; // Bueno, Moderado, Critico, SinDatos
  }

  public sealed class AbcItemDto
  {
    public string Sku { get; init; } = string.Empty;
    public string? Descripcion { get; init; }
    public long VentasTotal { get; init; }
    public double PorcentajeAcumulado { get; init; }
    public string Clasificacion { get; init; } = string.Empty; // A, B, C
  }

  public sealed class AbcSummaryDto
  {
    public int CantidadA { get; init; }
    public int CantidadB { get; init; }
    public int CantidadC { get; init; }
    public List<AbcItemDto> Items { get; init; } = new();
  }

  public sealed class VentasMensualesTrendDto
  {
    public string Periodo { get; init; } = string.Empty; // yyyy-MM
    public long TotalUnidades { get; init; }
    public int SkusActivos { get; init; }
  }
}
