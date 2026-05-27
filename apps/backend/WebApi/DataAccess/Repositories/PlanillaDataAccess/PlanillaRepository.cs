using WebApi.Data;
using WebApi.Models;

namespace DataAccess.Repositories.PlanillaDataAccess
{
  public class PlanillaRepository : IPlanillaRepository
  {
    private readonly EvalutiaDbContext _db;

    public PlanillaRepository(EvalutiaDbContext db)
    {
      _db = db;
    }

    public (IReadOnlyList<(PlanillaVentasCalculada Fila, string? Descripcion, string? MarcaNombre, string? GeneroDescripcion, int? StockMinimo)> Items, int TotalSkus) GetVentas(
        int page,
        int pageSize)
    {
      // SKUs distintos paginados, ordenados alfabéticamente
      var skusPaginados = _db.PlanillasVentasCalculadas
          .Select(p => p.Sku)
          .Distinct()
          .OrderBy(s => s)
          .Skip((page - 1) * pageSize)
          .Take(pageSize)
          .ToList();

      var totalSkus = _db.PlanillasVentasCalculadas
          .Select(p => p.Sku)
          .Distinct()
          .Count();

      if (!skusPaginados.Any())
        return (new List<(PlanillaVentasCalculada, string?, string?, string?, int?)>(), totalSkus);

      // Filas de planilla para los SKUs del page
      var filas = (from p in _db.PlanillasVentasCalculadas
                   join a in _db.Articulos on p.Sku equals a.Sku into aj
                   from a in aj.DefaultIfEmpty()
                   where skusPaginados.Contains(p.Sku)
                   select new
                   {
                     p.Sku,
                     p.Year,
                     p.Month,
                     p.VentasCantidad,
                     p.DiasConStock,
                     p.DiasNaturalesMes,
                     p.RotacionDiariaReal,
                     p.RotacionDiariaBruta,
                     p.RotacionDiariaDesestacionalizada,
                     p.EstadoMes,
                     Descripcion = a != null ? a.Descripcion : null,
                     MarcaNombre = a != null ? a.MarcaNombre : null,
                     GeneroDescripcion = a != null ? a.GeneroDescripcion : null,
                     StockMinimo = a != null ? (int?)a.StockMinimo : null
                   })
                  .ToList();

      var result = filas.Select(f => (
          Fila: new PlanillaVentasCalculada
          {
            Sku = f.Sku,
            Year = f.Year,
            Month = f.Month,
            VentasCantidad = f.VentasCantidad,
            DiasConStock = f.DiasConStock,
            DiasNaturalesMes = f.DiasNaturalesMes,
            RotacionDiariaReal = f.RotacionDiariaReal,
            RotacionDiariaBruta = f.RotacionDiariaBruta,
            RotacionDiariaDesestacionalizada = f.RotacionDiariaDesestacionalizada,
            EstadoMes = f.EstadoMes
          },
          Descripcion: f.Descripcion,
          MarcaNombre: f.MarcaNombre,
          GeneroDescripcion: f.GeneroDescripcion,
          StockMinimo: f.StockMinimo
      )).ToList();

      return (result, totalSkus);
    }

    public (List<(uint Id, string Nombre)> Marcas, List<(uint Id, string Nombre)> Generos, int SinMarca, int SinGenero) GetFiltros()
    {
      var skusEnPlanilla = _db.PlanillasVentasCalculadas.Select(p => p.Sku).Distinct();

      var marcas = _db.Articulos
          .Where(a => skusEnPlanilla.Contains(a.Sku) && a.MarcaId != null)
          .GroupBy(a => a.MarcaId)
          .Select(g => new { Id = g.Key!.Value, Nombre = g.Max(a => a.MarcaNombre) })
          .OrderBy(m => m.Nombre)
          .AsEnumerable()
          .Select(m => (m.Id, m.Nombre ?? ""))
          .ToList();

      var generos = _db.Articulos
          .Where(a => skusEnPlanilla.Contains(a.Sku) && a.GeneroId != null)
          .GroupBy(a => a.GeneroId)
          .Select(g => new { Id = g.Key!.Value, Nombre = g.Max(a => a.GeneroDescripcion) })
          .OrderBy(g => g.Nombre)
          .AsEnumerable()
          .Select(g => (g.Id, g.Nombre ?? ""))
          .ToList();

      var sinMarca = _db.Articulos.Count(a => skusEnPlanilla.Contains(a.Sku) && a.MarcaId == null);
      var sinGenero = _db.Articulos.Count(a => skusEnPlanilla.Contains(a.Sku) && a.GeneroId == null);

      return (marcas, generos, sinMarca, sinGenero);
    }
  }
}
