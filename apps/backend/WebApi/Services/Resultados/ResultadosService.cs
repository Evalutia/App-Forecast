using WebApi.Models;
using WebApi.Data;
using Microsoft.EntityFrameworkCore;

namespace Services.Resultados
{
  public class ResultadosService : IResultadosService
  {
    private readonly EvalutiaDbContext _db;

    public ResultadosService(EvalutiaDbContext db)
    {
      _db = db;
    }

    // Ventana calendario de StockResumen365 (issue #120, ver run_calc_stock_resumen.py
    // VENTANA_DIAS). StockResumen365.TotalDias NO es esto -- cuenta COUNT(agg.fecha),
    // dias con registro real en stock_diario, no dias calendario. Un articulo cuyo feed
    // solo escribe filas mientras tiene stock llega con TotalDias == DiasConStock, asi
    // que usarlo como denominador de la tasa de quiebre da 0% siempre, sin importar
    // cuanto tiempo estuvo sin stock. La planilla (run_calc_planilla.py,
    // dias_naturales_mes) usa el calendario como denominador -- un dia sin registro
    // cuenta como sin stock ahi, no se excluye. Replicamos ese criterio: los dias sin
    // registro en la ventana se presumen sin stock.
    private const int VentanaDiasStock = 365;

    // SKUs elegibles para modelo econométrico (issue #94: migrado de grupos.aplica_modelo_econometrico,
    // flag muerto desde #71, a articulos_elegibilidad_econometrico.elegible -- mismo criterio que
    // get_skus_modelo.py usa desde #71, este servicio nunca se había actualizado). Evita que predicciones
    // generadas antes de que un SKU perdiera elegibilidad (issue #57) sigan filtrándose a los
    // promedios/pronósticos de Resultados.
    private HashSet<string> GetSkusElegiblesModelo()
    {
      return _db.ArticulosElegibilidadEconometrico
        .AsNoTracking()
        .Where(e => e.Elegible)
        .Select(e => e.Sku)
        .ToHashSet();
    }

    public ResumenGlobalDto GetResumenGlobal()
    {
      // SKUs con stock_minimo definido (mismo universo que antes)
      var skusConStock = _db.Articulos
        .AsNoTracking()
        .Where(a => a.StockMinimo > 0)
        .Select(a => a.Sku)
        .ToHashSet();

      // Resumen precalculado por el ETL nocturno (issue #59/#60) — reemplaza la
      // agregación en vivo de stock_diario (25M+ filas), que era la causa real del
      // timeout en producción con el catálogo ampliado (~5500 SKUs). Guarda solo
      // conteos crudos; la fórmula de stockout/ventas-perdidas sigue siendo la misma
      // de acá abajo, solo cambia el origen del dato.
      var resumen = _db.StockResumen365
        .AsNoTracking()
        .ToList()
        .Where(r => skusConStock.Contains(r.Sku))
        .ToList();

      int totalSkus = resumen.Count;
      int skusConStockout = 0;
      double sumStockoutRate = 0;
      long ventasPerdidasTotal = 0;

      foreach (var r in resumen)
      {
        // Issue #120: mismo criterio que GetStockAnalysis/GetStockoutDistribution --
        // sin ningun dia observado no hay señal para presumir quiebre.
        if (r.TotalDias <= 0) continue;

        var diasSinStock = Math.Max(VentanaDiasStock - r.DiasConStock, 0);
        var stockoutRate = (double)diasSinStock / VentanaDiasStock * 100;
        sumStockoutRate += stockoutRate;
        if (diasSinStock > 0) skusConStockout++;

        if (r.DiasConStock > 0 && r.Ventas365 > 0)
        {
          var ventasPorDia = (double)r.Ventas365 / r.DiasConStock;
          ventasPerdidasTotal += (long)(ventasPorDia * diasSinStock);
        }
      }

      // R² promedio de las últimas predicciones (solo SKUs actualmente elegibles — issue #57)
      var skusElegiblesModelo = GetSkusElegiblesModelo();
      var predicciones = _db.Predicciones
        .AsNoTracking()
        .Where(p => p.R2 != null && skusElegiblesModelo.Contains(p.Sku))
        .GroupBy(p => new { p.Sku, p.Modelo })
        .Select(g => g.OrderByDescending(p => p.TsGeneracion).First())
        .ToList();

      var r2Promedio = predicciones.Any() ? predicciones.Average(p => p.R2 ?? 0) : 0;

      var ultimaPrediccion = _db.Predicciones
        .AsNoTracking()
        .OrderByDescending(p => p.TsGeneracion)
        .Select(p => p.TsGeneracion)
        .FirstOrDefault();

      return new ResumenGlobalDto
      {
        TotalSkus = totalSkus,
        SkusConStockout = skusConStockout,
        StockoutRatePromedio = totalSkus > 0 ? Math.Round(sumStockoutRate / totalSkus, 1) : 0,
        VentasPerdidasTotales = ventasPerdidasTotal,
        R2Promedio = Math.Round(r2Promedio, 3),
        UltimaPrediccion = ultimaPrediccion != default ? ultimaPrediccion.ToString("yyyy-MM-dd") : null
      };
    }

    public int CountStockAnalysis(string? sku)
    {
      var q = _db.Articulos.AsNoTracking().AsQueryable();
      if (!string.IsNullOrWhiteSpace(sku))
        q = q.Where(a => a.Sku.ToLower().StartsWith(sku.ToLower()));
      return q.Count();
    }

    public IReadOnlyList<SkuStockAnalysisDto> GetStockAnalysis(string? sku, string? orderBy, int page, int pageSize)
    {
      page = Math.Max(1, page);
      pageSize = Math.Clamp(pageSize, 1, 200);

      var today = DateOnly.FromDateTime(DateTime.UtcNow.Date);

      // Get articulos (paginated)
      var artQ = _db.Articulos.AsNoTracking().AsQueryable();
      if (!string.IsNullOrWhiteSpace(sku))
        artQ = artQ.Where(a => a.Sku.ToLower().StartsWith(sku.ToLower()));

      var articulos = artQ.OrderBy(a => a.Sku).ToList();
      var skuList = articulos.Select(a => a.Sku).ToList();

      // Resumen precalculado de stock_diario por el ETL nocturno (issue #59/#60) —
      // cubre todos los SKUs de articulos, no solo stock_minimo > 0 (esta función,
      // a diferencia de las otras 3 de este archivo, no filtra por ese umbral).
      var resumen = _db.StockResumen365
        .AsNoTracking()
        .ToList()
        .ToDictionary(r => r.Sku);

      // Predicciones (próximo trimestre, modelo COMBINADA preferido; solo SKUs elegibles — issue #57)
      var skusElegiblesModelo = GetSkusElegiblesModelo();
      var predicciones = _db.Predicciones
        .AsNoTracking()
        .Where(p => skuList.Contains(p.Sku) && p.FechaPredicha >= today && skusElegiblesModelo.Contains(p.Sku))
        .ToList()
        .GroupBy(p => p.Sku)
        .ToDictionary(g => g.Key, g =>
        {
          var combinada = g.Where(p => p.Modelo == "COMBINADA")
                           .OrderBy(p => p.FechaPredicha)
                           .FirstOrDefault();
          return combinada ?? g.OrderBy(p => p.FechaPredicha).FirstOrDefault();
        });

      var results = new List<SkuStockAnalysisDto>();
      const int MIN_DIAS_STOCK = 30; // mínimo de días con datos para que el cálculo sea confiable

      foreach (var art in articulos)
      {
        var minStock = art.StockMinimo;
        var r = resumen.TryGetValue(art.Sku, out var rr) ? rr : null;

        int totalDias = r?.TotalDias ?? 0;
        int diasConStock = r?.DiasConStock ?? 0;
        int ventas365 = (int)(r?.Ventas365 ?? 0);

        // Sin ningun dia observado (r == null, articulo recien dado de alta y aun
        // no procesado por el ETL nocturno) no hay señal para presumir quiebre --
        // a diferencia del caso "feed parcial" (totalDias > 0), acá no sabemos nada.
        bool tieneDatos = totalDias > 0;
        var diasSinStock = tieneDatos ? Math.Max(VentanaDiasStock - diasConStock, 0) : 0;
        var stockoutRate = tieneDatos ? (double)diasSinStock / VentanaDiasStock * 100 : 0;

        // Solo calcular velocidad de venta si hay suficientes días de datos (>= 30)
        bool dataSuficiente = totalDias >= MIN_DIAS_STOCK;
        double? ventasPorDia = (dataSuficiente && diasConStock > 0) ? (double)ventas365 / diasConStock : null;
        int? ventasPerdidas = (dataSuficiente && ventasPorDia.HasValue) ? (int)(ventasPorDia.Value * diasSinStock) : null;

        int? pronostico = null;
        if (predicciones.ContainsKey(art.Sku) && predicciones[art.Sku] != null)
          pronostico = (int)Math.Ceiling(predicciones[art.Sku]!.CantidadPredicha);

        // Sugerencia de compra para 90 días (ciclo de compra ~3 meses)
        int? sugerencia = ventasPorDia.HasValue ? (int)Math.Ceiling(ventasPorDia.Value * 90 * 1.15) : null;

        results.Add(new SkuStockAnalysisDto
        {
          Sku = art.Sku,
          Descripcion = art.Descripcion,
          StockMinimo = minStock,
          Ventas365 = ventas365,
          DiasConStock365 = diasConStock,
          DiasSinStock365 = diasSinStock,
          VentasPorDiaConStock365 = ventasPorDia.HasValue ? Math.Round(ventasPorDia.Value, 2) : null,
          StockoutRate365 = Math.Round(stockoutRate, 1),
          VentasPerdidasEstimadas365 = ventasPerdidas,
          PronosticoProximoTrimestre = pronostico,
          SugerenciaCompra90 = sugerencia
        });
      }

      // Sorting
      var sorted = (orderBy?.ToLower()) switch
      {
        "stockout" => results.OrderByDescending(r => r.StockoutRate365).ThenBy(r => r.Sku),
        "ventasperdidas" => results.OrderByDescending(r => r.VentasPerdidasEstimadas365 ?? 0).ThenBy(r => r.Sku),
        "ventas" => results.OrderByDescending(r => r.Ventas365).ThenBy(r => r.Sku),
        _ => results.OrderBy(r => r.Sku).AsEnumerable()
      };

      return sorted.Skip((page - 1) * pageSize).Take(pageSize).ToList();
    }

    public IReadOnlyList<TopVentasPerdidasDto> GetTopVentasPerdidas(int top)
    {
      top = Math.Clamp(top, 1, 50);

      var skusConStock = _db.Articulos.AsNoTracking()
        .Where(a => a.StockMinimo > 0)
        .Select(a => new { a.Sku, a.Descripcion })
        .ToList();

      // Resumen precalculado de stock_diario por el ETL nocturno (issue #59/#60).
      var resumen = _db.StockResumen365.AsNoTracking().ToList().ToDictionary(r => r.Sku);

      const int MIN_DIAS = 30;
      var results = new List<TopVentasPerdidasDto>();

      foreach (var s in skusConStock)
      {
        if (!resumen.TryGetValue(s.Sku, out var r)) continue;
        if (r.TotalDias < MIN_DIAS) continue;
        if (r.DiasConStock <= 0 || r.Ventas365 <= 0) continue;
        var ventasPorDia = (double)r.Ventas365 / r.DiasConStock;
        var diasSinStock = Math.Max(VentanaDiasStock - r.DiasConStock, 0);
        var perdidas = (int)(ventasPorDia * diasSinStock);
        if (perdidas <= 0) continue;
        results.Add(new TopVentasPerdidasDto
        {
          Sku = s.Sku,
          Descripcion = s.Descripcion,
          VentasPerdidas = perdidas
        });
      }

      return results.OrderByDescending(r => r.VentasPerdidas).Take(top).ToList();
    }

    public StockoutDistributionDto GetStockoutDistribution()
    {
      var skusConStock = _db.Articulos.AsNoTracking()
        .Where(a => a.StockMinimo > 0)
        .Select(a => new { a.Sku, a.Descripcion })
        .ToList();

      // Resumen precalculado de stock_diario por el ETL nocturno (issue #59/#60).
      var resumen = _db.StockResumen365.AsNoTracking().ToList().ToDictionary(r => r.Sku);

      const int MIN_DIAS = 30;
      int bueno = 0, moderado = 0, critico = 0, sinDatos = 0;
      var items = new List<StockoutItemDto>();

      foreach (var s in skusConStock)
      {
        if (!resumen.TryGetValue(s.Sku, out var r) || r.TotalDias < MIN_DIAS)
        {
          sinDatos++;
          items.Add(new StockoutItemDto { Sku = s.Sku, Descripcion = s.Descripcion, StockoutRate = -1, Categoria = "SinDatos" });
          continue;
        }
        var diasSinStock = Math.Max(VentanaDiasStock - r.DiasConStock, 0);
        var rate = (double)diasSinStock / VentanaDiasStock * 100;
        string cat;
        if (rate > 30) { critico++; cat = "Critico"; }
        else if (rate > 15) { moderado++; cat = "Moderado"; }
        else { bueno++; cat = "Bueno"; }
        items.Add(new StockoutItemDto { Sku = s.Sku, Descripcion = s.Descripcion, StockoutRate = Math.Round(rate, 1), Categoria = cat });
      }

      return new StockoutDistributionDto
      {
        Bueno = bueno,
        Moderado = moderado,
        Critico = critico,
        SinDatos = sinDatos,
        Items = items
      };
    }

    public AbcSummaryDto GetAbcClassification()
    {
      var today = DateOnly.FromDateTime(DateTime.UtcNow.Date);
      var desde365 = today.AddDays(-365);

      var ventasPorSku = _db.VentasHistoricas.AsNoTracking()
        .Where(v => v.Fecha >= desde365 && v.Fecha <= today)
        .GroupBy(v => v.Sku)
        .Select(g => new { Sku = g.Key, Total = g.Sum(x => (long)x.Cantidad) })
        .OrderByDescending(x => x.Total)
        .ToList();

      var descMap = _db.Articulos.AsNoTracking()
        .ToDictionary(a => a.Sku, a => a.Descripcion);

      // Issue #82: granTotal solo suma SKUs con Total > 0 (el "pastel" real de ventas
      // positivas). Con notas de credito reales, un SKU de neto negativo/cero puede
      // hacer que el acumulado supere el 100% antes de terminar de recorrer la lista
      // si se incluye en granTotal -- rompe la clasificacion A/B/C de todos los
      // siguientes. Esos SKUs se clasifican "C" directamente, sin participar del
      // acumulado, pero siguen apareciendo en la lista por transparencia.
      long granTotal = ventasPorSku.Where(x => x.Total > 0).Sum(x => x.Total);
      if (granTotal == 0) return new AbcSummaryDto();

      double acum = 0;
      var items = new List<AbcItemDto>();
      int cantA = 0, cantB = 0, cantC = 0;

      foreach (var v in ventasPorSku)
      {
        string clasif;
        if (v.Total <= 0)
        {
          clasif = "C";
        }
        else
        {
          acum += (double)v.Total / granTotal * 100;
          clasif = acum <= 80 ? "A" : acum <= 95 ? "B" : "C";
        }

        if (clasif == "A") cantA++;
        else if (clasif == "B") cantB++;
        else cantC++;

        items.Add(new AbcItemDto
        {
          Sku = v.Sku,
          Descripcion = descMap.ContainsKey(v.Sku) ? descMap[v.Sku] : null,
          VentasTotal = v.Total,
          PorcentajeAcumulado = Math.Round(acum, 1),
          Clasificacion = clasif
        });
      }

      return new AbcSummaryDto
      {
        CantidadA = cantA,
        CantidadB = cantB,
        CantidadC = cantC,
        Items = items
      };
    }

    public IReadOnlyList<VentasMensualesTrendDto> GetVentasMensualesTrend(int meses)
    {
      meses = Math.Clamp(meses, 3, 36);
      var today = DateOnly.FromDateTime(DateTime.UtcNow.Date);
      var desde = today.AddMonths(-meses);

      var raw = _db.VentasHistoricas.AsNoTracking()
        .Where(v => v.Fecha >= desde && v.Fecha <= today)
        .GroupBy(v => new { v.Fecha.Year, v.Fecha.Month })
        .Select(g => new
        {
          g.Key.Year,
          g.Key.Month,
          TotalUnidades = g.Sum(x => (long)x.Cantidad),
          // Issue #64/#120: ventas_historicas guarda una fila por SKU por dia
          // calendario aunque no haya venta real (cantidad=0). Sin este filtro,
          // Distinct() cuenta el catalogo entero como "activo".
          SkusActivos = g.Where(x => x.Cantidad > 0).Select(x => x.Sku).Distinct().Count()
        })
        .ToList();

      return raw
        .Select(g => new VentasMensualesTrendDto
        {
          Periodo = $"{g.Year}-{g.Month:D2}",
          TotalUnidades = g.TotalUnidades,
          SkusActivos = g.SkusActivos
        })
        .OrderBy(x => x.Periodo)
        .ToList();
    }
  }
}
