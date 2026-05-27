using DataAccess.Repositories.PlanillaDataAccess;

namespace Services.Planilla
{
  public class PlanillaService : IPlanillaService
  {
    private readonly IPlanillaRepository _repo;

    public PlanillaService(IPlanillaRepository repo)
    {
      _repo = repo;
    }

    public (IReadOnlyList<PlanillaSkuDto> Items, int TotalSkus) GetVentas(int page, int pageSize)
    {
      if (page < 1)
        throw new InvalidOperationException("page debe ser >= 1");

      if (pageSize is < 1 or > 200)
        throw new InvalidOperationException("pageSize fuera de rango (1..200)");

      var (filas, totalSkus) = _repo.GetVentas(page, pageSize);

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
              MarcaNombre     = primera.MarcaNombre,
              GeneroDescripcion = primera.GeneroDescripcion,
              StockMinimo     = primera.StockMinimo,
              Meses           = g
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
                    EstadoMes                      = f.Fila.EstadoMes
                  })
                  .ToList()
            };
          })
          .OrderBy(s => s.Sku)
          .ToList();

      return (items, totalSkus);
    }

    public PlanillaFiltrosDto GetFiltros()
    {
      var (marcas, generos, sinMarca, sinGenero) = _repo.GetFiltros();

      return new PlanillaFiltrosDto
      {
        Marcas  = marcas.Select(m => new PlanillaFiltroItemDto { Id = m.Id, Nombre = m.Nombre }).ToList(),
        Generos = generos.Select(g => new PlanillaFiltroItemDto { Id = g.Id, Nombre = g.Nombre }).ToList(),
        ArticulosIncompletos = new PlanillaArticulosIncompletosDto
        {
          SinMarca  = sinMarca,
          SinGenero = sinGenero
        }
      };
    }
  }
}
