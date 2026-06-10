using WebApi.Models;

namespace Services.Planilla
{
  public interface IPlanillaService
  {
    (IReadOnlyList<PlanillaSkuDto> Items, int TotalSkus) GetVentas(int page, int pageSize, uint? marcaId = null, uint? generoId = null, string? estadoMes = null);
    PlanillaFiltrosDto GetFiltros();
    IReadOnlyList<PlanillaSugerenciaDto> GetSugerencias();
  }

  public sealed class PlanillaSugerenciaDto
  {
    public string Sku { get; init; } = string.Empty;
    public decimal? RotacionSugerida { get; init; }
    public decimal? FiabilidadPorcentaje { get; init; }
    public decimal? DiasHastaQuiebre { get; init; }
  }

  public sealed class PlanillaFiltroItemDto
  {
    public uint Id { get; init; }
    public string Nombre { get; init; } = string.Empty;
  }

  public sealed class PlanillaArticulosIncompletosDto
  {
    public int SinMarca { get; init; }
    public int SinGenero { get; init; }
  }

  public sealed class PlanillaFiltrosDto
  {
    public IReadOnlyList<PlanillaFiltroItemDto> Marcas { get; init; } = [];
    public IReadOnlyList<PlanillaFiltroItemDto> Generos { get; init; } = [];
    public PlanillaArticulosIncompletosDto ArticulosIncompletos { get; init; } = new();
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
    public string? FrecuenciaNivel { get; init; }
    public decimal? RotacionAjustada { get; init; }
  }
}
