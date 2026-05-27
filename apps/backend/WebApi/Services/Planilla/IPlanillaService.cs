using WebApi.Models;

namespace Services.Planilla
{
  public interface IPlanillaService
  {
    (IReadOnlyList<PlanillaSkuDto> Items, int TotalSkus) GetVentas(int page, int pageSize);
  }

  public sealed class PlanillaSkuDto
  {
    public string Sku { get; init; } = string.Empty;
    public string? Descripcion { get; init; }
    public string? MarcaNombre { get; init; }
    public string? GeneroDescripcion { get; init; }
    public int? StockMinimo { get; init; }
    public IReadOnlyList<PlanillaMesDto> Meses { get; init; } = [];
  }

  public sealed class PlanillaMesDto
  {
    public int Year { get; init; }
    public int Month { get; init; }
    public long VentasCantidad { get; init; }
    public int DiasConStock { get; init; }
    public int DiasNaturalesMes { get; init; }
    public decimal? RotacionDiariaReal { get; init; }
    public decimal? RotacionDiariaBruta { get; init; }
    public decimal? RotacionDiariaDesestacionalizada { get; init; }
    public string EstadoMes { get; init; } = string.Empty;
  }
}
