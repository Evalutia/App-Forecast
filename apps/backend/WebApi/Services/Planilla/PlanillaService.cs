using DataAccess.Repositories.PlanillaDataAccess;

namespace Services.Planilla
{
  public class PlanillaService : IPlanillaService
  {
    private readonly IPlanillaRepository _repo;

    // Estado sintético (#106): marca un mes de la ventana sin fila calculada en
    // planilla_ventas_calculada. No existe en la DB ni es filtrable — solo
    // normaliza la respuesta para que todos los SKUs tengan la misma ventana.
    public const string EstadoSinDatos = "sin_datos";

    private static readonly HashSet<string> _estadosValidos =
        ["normal", "quiebre_parcial", "sin_stock"];

    private static readonly HashSet<string> _criteriosValidos =
        ["historico", "promedio", "real_extrapolado"];

    public PlanillaService(IPlanillaRepository repo)
    {
      _repo = repo;
    }

    public (IReadOnlyList<PlanillaSkuDto> Items, int TotalSkus) GetVentas(
        int page,
        int pageSize,
        uint? marcaId = null,
        uint? generoId = null,
        uint? grupoId = null,
        string? estadoMes = null,
        string? criterioFrecuencia = null)
    {
      if (page < 1)
        throw new InvalidOperationException("page debe ser >= 1");

      if (pageSize is < 1 or > 200)
        throw new InvalidOperationException("pageSize fuera de rango (1..200)");

      if (estadoMes != null && !_estadosValidos.Contains(estadoMes))
        throw new ArgumentException(
            $"Valor inválido '{estadoMes}'. Permitidos: {string.Join(", ", _estadosValidos)}",
            nameof(estadoMes));

      if (criterioFrecuencia != null && !_criteriosValidos.Contains(criterioFrecuencia))
        throw new ArgumentException(
            $"Valor inválido '{criterioFrecuencia}'. Permitidos: {string.Join(", ", _criteriosValidos)}",
            nameof(criterioFrecuencia));

      var (filas, totalSkus) = _repo.GetVentas(page, pageSize, marcaId, generoId, grupoId, estadoMes, criterioFrecuencia);
      var ventana = _repo.GetVentanaMeses();

      // Pivot tall → wide: agrupar filas por SKU y construir array de meses
      var items = filas
          .GroupBy(f => f.Fila.Sku)
          .Select(g =>
          {
            var primera = g.First();
            return new PlanillaSkuDto
            {
              Sku             = g.Key,
              Descripcion     = primera.Descripcion,
              CodigoBarras    = primera.CodigoBarras,
              MarcaNombre     = primera.MarcaNombre,
              GeneroDescripcion = primera.GeneroDescripcion,
              StockMinimo     = primera.StockMinimo,
              EstadoArticulo  = primera.EstadoArticulo,
              Meses           = NormalizarVentana(g
                  .OrderBy(f => f.Fila.Year)
                  .ThenBy(f => f.Fila.Month)
                  .Select(f => new PlanillaMesDto
                  {
                    Year                           = f.Fila.Year,
                    Month                          = f.Fila.Month,
                    VentasCantidad                 = f.Fila.VentasCantidad,
                    DiasConStock                   = f.Fila.DiasConStock,
                    DiasNaturalesMes               = f.Fila.DiasNaturalesMes,
                    RotacionDiariaReal             = f.Fila.RotacionDiariaReal,
                    RotacionDiariaBruta            = f.Fila.RotacionDiariaBruta,
                    RotacionDiariaDesestacionalizada = f.Fila.RotacionDiariaDesestacionalizada,
                    EstadoMes                      = f.Fila.EstadoMes,
                    FrecuenciaNivel                = f.Fila.FrecuenciaNivel,
                    RotacionAjustada               = f.Fila.RotacionAjustada,
                    TicketsMes                     = f.Fila.TicketsMes,
                    ValorHistorico                 = f.Fila.ValorHistorico,
                    ValorAjustado                  = f.Fila.ValorAjustado,
                    CriterioFrecuencia             = f.Fila.CriterioFrecuencia,
                    VentaOExtrapolacion            = f.Fila.VentaOExtrapolacion
                  })
                  .ToList(), ventana)
            };
          })
          .OrderBy(s => s.Sku)
          .ToList();

      return (items, totalSkus);
    }

    /// <summary>
    /// Issue #106: todo SKU sale con exactamente la misma ventana de meses (la
    /// global de la tabla), rellenando faltantes —prefijo corto, hueco en el
    /// medio, o cola sin mes vigente— con placeholders "sin_datos". Garantiza a
    /// los consumidores (tabla web, export Excel) que las posiciones de mes son
    /// comparables entre filas y que el último elemento es el mes de referencia.
    /// </summary>
    private static IReadOnlyList<PlanillaMesDto> NormalizarVentana(
        List<PlanillaMesDto> meses,
        ((int Year, int Month) Min, (int Year, int Month) Max)? ventana)
    {
      if (ventana == null)
        return meses;

      var (min, max) = ventana.Value;
      var porMes = meses.ToDictionary(m => (m.Year, m.Month));

      var resultado = new List<PlanillaMesDto>();
      for (var idx = min.Year * 12 + min.Month; idx <= max.Year * 12 + max.Month; idx++)
      {
        var year  = (idx - 1) / 12;
        var month = (idx - 1) % 12 + 1;
        resultado.Add(porMes.TryGetValue((year, month), out var real)
            ? real
            : new PlanillaMesDto
            {
              Year             = year,
              Month            = month,
              DiasNaturalesMes = DateTime.DaysInMonth(year, month),
              EstadoMes        = EstadoSinDatos
              // El resto (VentasCantidad, DiasConStock, TicketsMes, rotaciones,
              // valores de blending) queda null: "no hay dato", no un 0 real.
            });
      }
      return resultado;
    }

    public IReadOnlyList<PlanillaSugerenciaDto> GetSugerencias()
    {
      return _repo.GetSugerencias()
          .Select(s => new PlanillaSugerenciaDto
          {
            Sku                  = s.Sku,
            RotacionSugerida     = s.RotacionSugerida,
            FiabilidadPorcentaje = s.FiabilidadPorcentaje,
            DiasHastaQuiebre     = s.DiasHastaQuiebre
          })
          .ToList();
    }

    public PlanillaFiltrosDto GetFiltros(uint? grupoId = null)
    {
      var (marcas, generos, grupos, sinMarca, sinGenero) = _repo.GetFiltros(grupoId);

      return new PlanillaFiltrosDto
      {
        Marcas  = marcas.Select(m => new PlanillaFiltroItemDto { Id = m.Id, Nombre = m.Nombre }).ToList(),
        Generos = generos.Select(g => new PlanillaFiltroItemDto { Id = g.Id, Nombre = g.Nombre }).ToList(),
        Grupos  = grupos.Select(g => new PlanillaFiltroItemDto { Id = g.Id, Nombre = g.Nombre }).ToList(),
        ArticulosIncompletos = new PlanillaArticulosIncompletosDto
        {
          SinMarca  = sinMarca,
          SinGenero = sinGenero
        }
      };
    }
  }
}
