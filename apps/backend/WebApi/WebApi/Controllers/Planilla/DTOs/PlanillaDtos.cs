using Services.Planilla;

namespace WebApi.Controllers.Planilla.DTOs
{
  public sealed class PlanillaVentasOutDto
  {
    public string Sku { get; init; } = string.Empty;
    public string? Descripcion { get; init; }
    public string? CodigoBarras { get; init; }
    public string? MarcaNombre { get; init; }
    public string? GeneroDescripcion { get; init; }
    public int? StockMinimo { get; init; }
    public string EstadoArticulo { get; init; } = "activo";
    public IReadOnlyList<PlanillaMesOutDto> Meses { get; init; } = [];

    public PlanillaVentasOutDto(PlanillaSkuDto dto)
    {
      Sku               = dto.Sku;
      Descripcion       = dto.Descripcion;
      CodigoBarras      = dto.CodigoBarras;
      MarcaNombre       = dto.MarcaNombre;
      GeneroDescripcion = dto.GeneroDescripcion;
      StockMinimo       = dto.StockMinimo;
      EstadoArticulo    = dto.EstadoArticulo;
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
    public string? FrecuenciaNivel { get; init; }
    public decimal? RotacionAjustada { get; init; }

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
      FrecuenciaNivel                = dto.FrecuenciaNivel;
      RotacionAjustada               = dto.RotacionAjustada;
    }
  }

  public sealed class PlanillaFiltroItemOutDto
  {
    public uint Id { get; init; }
    public string Nombre { get; init; } = string.Empty;

    public PlanillaFiltroItemOutDto(PlanillaFiltroItemDto dto)
    {
      Id     = dto.Id;
      Nombre = dto.Nombre;
    }
  }

  public sealed class PlanillaArticulosIncompletosOutDto
  {
    public int SinMarca { get; init; }
    public int SinGenero { get; init; }

    public PlanillaArticulosIncompletosOutDto(PlanillaArticulosIncompletosDto dto)
    {
      SinMarca  = dto.SinMarca;
      SinGenero = dto.SinGenero;
    }
  }

  public sealed class PlanillaFiltrosOutDto
  {
    public IReadOnlyList<PlanillaFiltroItemOutDto> Marcas { get; init; } = [];
    public IReadOnlyList<PlanillaFiltroItemOutDto> Generos { get; init; } = [];
    public PlanillaArticulosIncompletosOutDto ArticulosIncompletos { get; init; }

    public PlanillaFiltrosOutDto(PlanillaFiltrosDto dto)
    {
      Marcas               = dto.Marcas.Select(m => new PlanillaFiltroItemOutDto(m)).ToList();
      Generos              = dto.Generos.Select(g => new PlanillaFiltroItemOutDto(g)).ToList();
      ArticulosIncompletos = new PlanillaArticulosIncompletosOutDto(dto.ArticulosIncompletos);
    }
  }

  public sealed class PlanillaSugerenciaOutDto
  {
    public string Sku { get; init; } = string.Empty;
    public decimal? RotacionSugerida { get; init; }
    public decimal? FiabilidadPorcentaje { get; init; }
    public decimal? DiasHastaQuiebre { get; init; }

    public PlanillaSugerenciaOutDto(PlanillaSugerenciaDto dto)
    {
      Sku                  = dto.Sku;
      RotacionSugerida     = dto.RotacionSugerida;
      FiabilidadPorcentaje = dto.FiabilidadPorcentaje;
      DiasHastaQuiebre     = dto.DiasHastaQuiebre;
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
