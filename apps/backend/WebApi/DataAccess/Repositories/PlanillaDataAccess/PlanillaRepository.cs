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

    public (IReadOnlyList<(PlanillaVentasCalculada Fila, string? Descripcion, string? MarcaNombre, string? GeneroDescripcion, int? StockMinimo, string EstadoArticulo, string? CodigoBarras)> Items, int TotalSkus) GetVentas(
        int page,
        int pageSize,
        uint? marcaId,
        uint? generoId,
        uint? grupoId,
        string? estadoMes)
    {
      // Query base sobre filas de planilla — el filtro estadoMes se aplica aquí,
      // antes del Distinct, lo que implementa la semántica "al menos un mes con ese estado"
      var planillaQuery = _db.PlanillasVentasCalculadas.AsQueryable();
      if (estadoMes != null)
        planillaQuery = planillaQuery.Where(p => p.EstadoMes == estadoMes);

      // IQueryable<string> compartido para Count y Skip/Take
      var skuQuery = planillaQuery.Select(p => p.Sku).Distinct();

      // Filtros de marca, género y grupo via subquery en articulos (→ IN SELECT sku FROM articulos WHERE ...)
      if (marcaId.HasValue || generoId.HasValue || grupoId.HasValue)
      {
        var articulosQuery = _db.Articulos.AsQueryable();
        if (marcaId.HasValue)
          articulosQuery = articulosQuery.Where(a => a.MarcaId == marcaId);
        if (generoId.HasValue)
          articulosQuery = articulosQuery.Where(a => a.GeneroId == generoId);
        if (grupoId.HasValue)
          articulosQuery = articulosQuery.Where(a => a.GrupoId == grupoId);
        var skusFiltrados = articulosQuery.Select(a => a.Sku);
        skuQuery = skuQuery.Where(s => skusFiltrados.Contains(s));
      }

      var totalSkus = skuQuery.Count();
      var skusPaginados = skuQuery.OrderBy(s => s).Skip((page - 1) * pageSize).Take(pageSize).ToList();

      if (!skusPaginados.Any())
        return (new List<(PlanillaVentasCalculada, string?, string?, string?, int?, string, string?)>(), totalSkus);

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
                     p.FrecuenciaNivel,
                     p.RotacionAjustada,
                     Descripcion = a != null ? a.Descripcion : null,
                     MarcaNombre = a != null ? a.MarcaNombre : null,
                     GeneroDescripcion = a != null ? a.GeneroDescripcion : null,
                     StockMinimo = a != null ? (int?)a.StockMinimo : null,
                     EstadoArticulo = a != null ? a.Estado : "activo",
                     CodigoBarras = a != null ? a.Barcode : null
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
            EstadoMes = f.EstadoMes,
            FrecuenciaNivel = f.FrecuenciaNivel,
            RotacionAjustada = f.RotacionAjustada
          },
          Descripcion: f.Descripcion,
          MarcaNombre: f.MarcaNombre,
          GeneroDescripcion: f.GeneroDescripcion,
          StockMinimo: f.StockMinimo,
          EstadoArticulo: f.EstadoArticulo,
          CodigoBarras: f.CodigoBarras
      )).ToList();

      return (result, totalSkus);
    }

    public (List<(uint Id, string Nombre)> Marcas, List<(uint Id, string Nombre)> Generos, List<(uint Id, string Nombre)> Grupos, int SinMarca, int SinGenero) GetFiltros(uint? grupoId)
    {
      var skusEnPlanilla = _db.PlanillasVentasCalculadas.Select(p => p.Sku).Distinct();

      // Marca/género/incompletos se acotan a grupoId cuando viene seteado, para no ofrecer
      // ni contar combinaciones grupo+marca/género que no existen.
      var articulosEnPlanilla = _db.Articulos.Where(a => skusEnPlanilla.Contains(a.Sku));
      if (grupoId.HasValue)
        articulosEnPlanilla = articulosEnPlanilla.Where(a => a.GrupoId == grupoId);

      var marcas = articulosEnPlanilla
          .Where(a => a.MarcaId != null)
          .GroupBy(a => a.MarcaId)
          .Select(g => new { Id = g.Key!.Value, Nombre = g.Max(a => a.MarcaNombre) })
          .OrderBy(m => m.Nombre)
          .AsEnumerable()
          .Select(m => (m.Id, m.Nombre ?? ""))
          .ToList();

      var generos = articulosEnPlanilla
          .Where(a => a.GeneroId != null)
          .GroupBy(a => a.GeneroId)
          .Select(g => new { Id = g.Key!.Value, Nombre = g.Max(a => a.GeneroDescripcion) })
          .OrderBy(g => g.Nombre)
          .AsEnumerable()
          .Select(g => (g.Id, g.Nombre ?? ""))
          .ToList();

      var sinMarca = articulosEnPlanilla.Count(a => a.MarcaId == null);
      var sinGenero = articulosEnPlanilla.Count(a => a.GeneroId == null);

      // Grupos disponibles: cruzados contra planilla (igual que marca/género) + visible_planilla,
      // independiente del grupoId pedido — es la lista de opciones del dropdown, no se acota a sí misma.
      var grupos = _db.Grupos
          .Where(g => g.VisiblePlanilla && _db.Articulos.Any(a => a.GrupoId == g.Id && skusEnPlanilla.Contains(a.Sku)))
          .OrderBy(g => g.Descripcion)
          .Select(g => new { g.Id, g.Descripcion })
          .AsEnumerable()
          .Select(g => (g.Id, g.Descripcion))
          .ToList();

      return (marcas, generos, grupos, sinMarca, sinGenero);
    }

    public IReadOnlyList<PlanillaSugerencias> GetSugerencias()
    {
      return _db.PlanillasSugerencias.OrderBy(s => s.Sku).ToList();
    }
  }
}
