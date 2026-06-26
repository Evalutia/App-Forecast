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

    // SKUs cuyo grupo tiene modelo econométrico habilitado (mismo criterio que get_skus_modelo.py de #43).
    // Evita que predicciones generadas antes de que un SKU perdiera elegibilidad (issue #57) sigan
    // filtrándose a los promedios/pronósticos de Resultados.
    private HashSet<string> GetSkusElegiblesModelo()
    {
      return _db.Articulos
        .AsNoTracking()
        .Join(_db.Grupos.AsNoTracking().Where(g => g.AplicaModeloEconometrico),
              a => a.GrupoId, g => g.Id, (a, g) => a.Sku)
        .ToHashSet();
    }

    public ResumenGlobalDto GetResumenGlobal()
    {
      var today = DateOnly.FromDateTime(DateTime.UtcNow.Date);
      var desde365 = today.AddDays(-365);

      // SKUs con stock_minimo definido y que tengan datos de stock
      var skusConStock = _db.Articulos
        .AsNoTracking()
        .Where(a => a.StockMinimo > 0)
        .Select(a => new { a.Sku, a.StockMinimo })
        .ToList();

      var skuSet = skusConStock.Select(s => s.Sku).ToHashSet();
      var minimos = skusConStock.ToDictionary(s => s.Sku, s => s.StockMinimo);

      // Stock diario de los últimos 365 días para esos SKUs
      var stockRows = _db.StockDiario
        .AsNoTracking()
        .Where(s => skuSet.Contains(s.Sku) && s.Fecha >= desde365 && s.Fecha <= today)
        .GroupBy(s => new { s.Sku, s.Fecha })
        .Select(g => new { g.Key.Sku, g.Key.Fecha, Total = (long)g.Sum(x => (long)x.Cantidad) })
        .ToList();

      // Agrupado por SKU una sola vez (issue #59) — antes cada SKU hacía stockRows.Where(...)
      // sobre la lista completa dentro de un foreach, O(totalSkus × totalFilas). Con ~4900 SKUs
      // y ~1.8M filas (post-rollout de grupos, #41-44) eso son ~10 mil millones de comparaciones
      // y la causa real del timeout en producción. Mismo patrón ya usado en GetStockAnalysis/
      // GetTopVentasPerdidas/GetStockoutDistribution.
      var stockPorSku = stockRows
        .GroupBy(r => r.Sku)
        .ToDictionary(g => g.Key, g => g.ToList());

      // Ventas perdidas totales
      var ventas365 = _db.VentasHistoricas
        .AsNoTracking()
        .Where(v => v.Fecha >= desde365 && v.Fecha <= today && skuSet.Contains(v.Sku))
        .GroupBy(v => v.Sku)
        .Select(g => new { Sku = g.Key, Total = g.Sum(x => (long)x.Cantidad) })
        .ToDictionary(x => x.Sku, x => x.Total);

      int totalSkus = skuSet.Count;
      int skusConStockout = 0;
      double sumStockoutRate = 0;
      long ventasPerdidasTotal = 0;

      // Un solo pase por SKU: antes el stockout y las ventas perdidas se calculaban en dos
      // foreach separados, recalculando diasConStock cada vez.
      foreach (var sku in skuSet)
      {
        var dias = stockPorSku.TryGetValue(sku, out var diasSku) ? diasSku : new();
        var diasConStock = dias.Count(d => d.Total > minimos[sku]);
        var totalDias = Math.Max(dias.Count, 1);
        var stockoutRate = (double)(totalDias - diasConStock) / totalDias * 100;
        sumStockoutRate += stockoutRate;
        if (diasConStock < totalDias) skusConStockout++;

        var diasSinStock = Math.Max(dias.Count - diasConStock, 0);
        if (diasConStock > 0 && ventas365.TryGetValue(sku, out var ventaTotal))
        {
          var ventasPorDia = (double)ventaTotal / diasConStock;
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
      var desde365 = today.AddDays(-365);

      // Get articulos (paginated)
      var artQ = _db.Articulos.AsNoTracking().AsQueryable();
      if (!string.IsNullOrWhiteSpace(sku))
        artQ = artQ.Where(a => a.Sku.ToLower().StartsWith(sku.ToLower()));

      var articulos = artQ.OrderBy(a => a.Sku).ToList();
      var skuList = articulos.Select(a => a.Sku).ToList();

      // Stock data for 365 days
      var stockData = _db.StockDiario
        .AsNoTracking()
        .Where(s => skuList.Contains(s.Sku) && s.Fecha >= desde365 && s.Fecha <= today)
        .GroupBy(s => new { s.Sku, s.Fecha })
        .Select(g => new { g.Key.Sku, g.Key.Fecha, Total = (long)g.Sum(x => (long)x.Cantidad) })
        .ToList()
        .GroupBy(x => x.Sku)
        .ToDictionary(g => g.Key, g => g.ToList());

      // Ventas 365 días
      var ventasData = _db.VentasHistoricas
        .AsNoTracking()
        .Where(v => skuList.Contains(v.Sku) && v.Fecha >= desde365 && v.Fecha <= today)
        .GroupBy(v => v.Sku)
        .Select(g => new { Sku = g.Key, Total = g.Sum(x => (long)x.Cantidad) })
        .ToDictionary(x => x.Sku, x => x.Total);

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
        var ventas365 = ventasData.ContainsKey(art.Sku) ? (int)ventasData[art.Sku] : 0;

        int diasConStock = 0;
        int totalDias = 0;

        if (stockData.ContainsKey(art.Sku))
        {
          var dias = stockData[art.Sku];
          totalDias = dias.Count;
          diasConStock = dias.Count(d => d.Total > minStock);
        }

        var diasSinStock = Math.Max(totalDias - diasConStock, 0);
        var stockoutRate = totalDias > 0 ? (double)diasSinStock / totalDias * 100 : 0;

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
          VentasPorDiaConStock365 = ventasPorDia.HasValue ? (double)Math.Ceiling(ventasPorDia.Value) : null,
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
      var today = DateOnly.FromDateTime(DateTime.UtcNow.Date);
      var desde365 = today.AddDays(-365);

      var skusConStock = _db.Articulos.AsNoTracking()
        .Where(a => a.StockMinimo > 0)
        .Select(a => new { a.Sku, a.Descripcion, a.StockMinimo })
        .ToList();
      var skuSet = skusConStock.Select(s => s.Sku).ToHashSet();
      var descMap = skusConStock.ToDictionary(s => s.Sku, s => s.Descripcion);
      var minimos = skusConStock.ToDictionary(s => s.Sku, s => s.StockMinimo);

      var stockRows = _db.StockDiario.AsNoTracking()
        .Where(s => skuSet.Contains(s.Sku) && s.Fecha >= desde365 && s.Fecha <= today)
        .GroupBy(s => new { s.Sku, s.Fecha })
        .Select(g => new { g.Key.Sku, g.Key.Fecha, Total = (long)g.Sum(x => (long)x.Cantidad) })
        .ToList()
        .GroupBy(x => x.Sku)
        .ToDictionary(g => g.Key, g => g.ToList());

      var ventas365 = _db.VentasHistoricas.AsNoTracking()
        .Where(v => v.Fecha >= desde365 && v.Fecha <= today && skuSet.Contains(v.Sku))
        .GroupBy(v => v.Sku)
        .Select(g => new { Sku = g.Key, Total = g.Sum(x => (long)x.Cantidad) })
        .ToDictionary(x => x.Sku, x => x.Total);

      const int MIN_DIAS = 30;
      var results = new List<TopVentasPerdidasDto>();

      foreach (var s in skusConStock)
      {
        if (!stockRows.ContainsKey(s.Sku)) continue;
        var dias = stockRows[s.Sku];
        if (dias.Count < MIN_DIAS) continue;
        var diasConStock = dias.Count(d => d.Total > minimos[s.Sku]);
        var diasSinStock = dias.Count - diasConStock;
        if (diasConStock <= 0 || !ventas365.ContainsKey(s.Sku)) continue;
        var ventasPorDia = (double)ventas365[s.Sku] / diasConStock;
        var perdidas = (int)(ventasPorDia * diasSinStock);
        if (perdidas <= 0) continue;
        results.Add(new TopVentasPerdidasDto
        {
          Sku = s.Sku,
          Descripcion = descMap[s.Sku],
          VentasPerdidas = perdidas
        });
      }

      return results.OrderByDescending(r => r.VentasPerdidas).Take(top).ToList();
    }

    public StockoutDistributionDto GetStockoutDistribution()
    {
      var today = DateOnly.FromDateTime(DateTime.UtcNow.Date);
      var desde365 = today.AddDays(-365);

      var skusConStock = _db.Articulos.AsNoTracking()
        .Where(a => a.StockMinimo > 0)
        .Select(a => new { a.Sku, a.StockMinimo, a.Descripcion })
        .ToList();
      var skuSet = skusConStock.Select(s => s.Sku).ToHashSet();
      var minimos = skusConStock.ToDictionary(s => s.Sku, s => s.StockMinimo);

      var stockRows = _db.StockDiario.AsNoTracking()
        .Where(s => skuSet.Contains(s.Sku) && s.Fecha >= desde365 && s.Fecha <= today)
        .GroupBy(s => new { s.Sku, s.Fecha })
        .Select(g => new { g.Key.Sku, g.Key.Fecha, Total = (long)g.Sum(x => (long)x.Cantidad) })
        .ToList()
        .GroupBy(x => x.Sku)
        .ToDictionary(g => g.Key, g => g.ToList());

      const int MIN_DIAS = 30;
      int bueno = 0, moderado = 0, critico = 0, sinDatos = 0;
      var items = new List<StockoutItemDto>();

      foreach (var s in skusConStock)
      {
        if (!stockRows.ContainsKey(s.Sku) || stockRows[s.Sku].Count < MIN_DIAS)
        {
          sinDatos++;
          items.Add(new StockoutItemDto { Sku = s.Sku, Descripcion = s.Descripcion, StockoutRate = -1, Categoria = "SinDatos" });
          continue;
        }
        var dias = stockRows[s.Sku];
        var diasConStock = dias.Count(d => d.Total > minimos[s.Sku]);
        var rate = (double)(dias.Count - diasConStock) / dias.Count * 100;
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

      long granTotal = ventasPorSku.Sum(x => x.Total);
      if (granTotal == 0) return new AbcSummaryDto();

      double acum = 0;
      var items = new List<AbcItemDto>();
      int cantA = 0, cantB = 0, cantC = 0;

      foreach (var v in ventasPorSku)
      {
        acum += (double)v.Total / granTotal * 100;
        string clasif = acum <= 80 ? "A" : acum <= 95 ? "B" : "C";
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
          SkusActivos = g.Select(x => x.Sku).Distinct().Count()
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
