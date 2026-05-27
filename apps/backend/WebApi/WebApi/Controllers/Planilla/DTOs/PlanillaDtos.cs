using Services.Planilla;

namespace WebApi.Controllers.Planilla.DTOs
{
  public sealed class PlanillaVentasOutDto
  {
    public string Sku { get; init; } = string.Empty;
    public string? Descripcion { get; init; }
    public string? MarcaNombre { get; init; }
    public string? GeneroDescripcion { get; init; }
    public int? StockMinimo { get; init; }
    public IReadOnlyList<PlanillaMesOutDto> Meses { get; init; } = [];

    public PlanillaVentasOutDto(PlanillaSkuDto dto)
    {
      Sku               = dto.Sku;
      Descripcion       = dto.Descripcion;
      MarcaNombre       = dto.MarcaNombre;
      GeneroDescripcion = dto.GeneroDescripcion;
      StockMinimo       = dto.StockMinimo;
      Meses             = dto.Meses.Select(m => new PlanillaMesOutDto(m)).ToList();
    }
  }

  public sealed class PlanillaMesOutDto
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

    public PlanillaMesOutDto(PlanillaMesDto dto)
    {
      Year                           = dto.Year;
      Month                          = dto.Month;
      VentasCantidad                 = dto.VentasCantidad;
      DiasConStock                   = dto.DiasConStock;
      DiasNaturalesMes               = dto.DiasNaturalesMes;
      RotacionDiariaReal             = dto.RotacionDiariaReal;
      RotacionDiariaBruta            = dto.RotacionDiariaBruta;
      RotacionDiariaDesestacionalizada = dto.RotacionDiariaDesestacionalizada;
      EstadoMes                      = dto.EstadoMes;
    }
  }

  public sealed class PagedResultDto<T>
  {
    public IEnumerable<T> Items { get; init; } = [];
    public int Page { get; init; }
    public int PageSize { get; init; }
    public int Total { get; init; }

    public PagedResultDto(IEnumerable<T> items, int page, int pageSize, int total)
    {
      Items    = items;
      Page     = page;
      PageSize = pageSize;
      Total    = total;
    }
  }
}
