using DataAccess.Repositories.VentaDataAccess;
using WebApi.Models;
using System;
using System.Collections.Generic;
using System.Linq;

namespace Services.Ventas
{
  public class VentasService : IVentasService
  {
    private readonly IVentaRepository _repo;

    public VentasService(IVentaRepository repo)
    {
      _repo = repo;
    }

    public (IReadOnlyList<VentaHistorica> Items, int Total) Search(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        int page,
        int pageSize)
    {
      if (page < 1)
        throw new InvalidOperationException("page debe ser >= 1");

      if (pageSize is < 1 or > 200)
        throw new InvalidOperationException("pageSize fuera de rango (1..200)");

      return _repo.Search(fechaDesde, fechaHasta, sku, page, pageSize);
    }

    public (IReadOnlyList<VentaAgregada> Items, int Total) Aggregate(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        string periodo,
        int page,
        int pageSize)
    {
      if (page < 1)
        throw new InvalidOperationException("page debe ser >= 1");

      if (pageSize is < 1 or > 200)
        throw new InvalidOperationException("pageSize fuera de rango (1..200)");

      return _repo.Aggregate(fechaDesde, fechaHasta, sku, periodo, page, pageSize);
    }

    public IReadOnlyList<string> DistinctSkus(string? filtro)
    {
      return _repo.DistinctSkus(filtro);
    }

    public IReadOnlyList<(string Sku, ulong TotalCantidad, double PorcentajeVentas, int? PronosticoProximoTrimestre)> TopSkusByVentas(DateOnly fechaDesde, DateOnly fechaHasta, int take)
    {
      if (fechaHasta < fechaDesde)
        throw new InvalidOperationException("fechaHasta debe ser >= fechaDesde");

      if (take < 1) take = 1;
      if (take > 200) take = 200;

      var todayDateOnly = DateOnly.FromDateTime(DateTime.Today);
      var fechaDesde12Meses = todayDateOnly.AddMonths(-12);

      var ventasFiltro = _repo.GetAllVentas()
          .Where(v => v.Fecha >= fechaDesde12Meses && v.Fecha <= todayDateOnly && v.Cantidad > 0)
          .ToList();

      var ventasPorSkuList = ventasFiltro
          .GroupBy(v => v.Sku)
          .Select(g => new
          {
            Sku = g.Key,
            Total = (ulong)g.Sum(x => (long)x.Cantidad),
            FechaPrimera = g.OrderBy(x => x.Fecha).Select(x => x.Fecha).FirstOrDefault()
          })
          .OrderByDescending(x => x.Total)
          .ThenBy(x => x.Sku)
          .Take(take)
          .ToList();

      var totalGeneral = ventasFiltro.Sum(v => (decimal)v.Cantidad);
      var skusList = ventasPorSkuList.Select(x => x.Sku).ToList();

      var predictions = _repo.GetAllPredicciones()
          .Where(p => skusList.Contains(p.Sku))
          .ToList();

      var pronosticos = predictions
          .GroupBy(p => p.Sku)
          .ToDictionary(
            g => g.Key,
            g => {
                var closest = g.OrderBy(p => Math.Abs((p.FechaPredicha.ToDateTime(TimeOnly.MinValue) - todayDateOnly.ToDateTime(TimeOnly.MinValue)).TotalDays))
                               .ThenBy(p => p.FechaPredicha)
                               .FirstOrDefault();
                return closest?.CantidadPredicha;
            }
          );

      var result = new List<(string Sku, ulong TotalCantidad, double PorcentajeVentas, int? PronosticoProximoTrimestre)>();
      foreach (var entry in ventasPorSkuList)
      {
        var sku = entry.Sku;
        var total = entry.Total;
        var porcentaje = totalGeneral > 0 ? (double)total / (double)totalGeneral * 100.0 : 0.0;
        var pronostico = pronosticos.ContainsKey(sku) ? (int?)Math.Ceiling(pronosticos[sku] ?? 0) : null;
        result.Add((sku, total, porcentaje, pronostico));
      }

      result.Add(("TOTAL", (ulong)totalGeneral, 100.0, null));
      return result;
    }

    public VentaSkuResumen GetSkuResumen(string sku, DateOnly today)
    {
      if (string.IsNullOrWhiteSpace(sku))
        throw new InvalidOperationException("sku es requerido");

      // Traemos todas las ventas del SKU
      var allSales = _repo.GetVentasBySku(sku).ToList();
      if (!allSales.Any())
      {
        return new VentaSkuResumen
        {
          Sku = sku,
          FechaPrimerObservacion = null,
          FechaUltimaObservacion = null,
          CantidadObservaciones = 0,
          MinimoVentasTrimestral = 0,
          TrimestreMinimoVentas = null,
          MaximoVentasTrimestral = 0,
          TrimestreMaximoVentas = null,
          PromedioVentasTrimestral = 0,
          VentasUltimoTrimestre = 0,
          UltimoTrimestre = null,
          VentasUltimoAnioCalendario = 0,
          CrecimientoVentasUltimoAnio = null,
          CrecimientoVentasUltimoTrimestreVsMismoTrimestreAnioAnterior = null,
          IncidenciaVentasUltimoAnioPorcentaje = null,
          IncidenciaVentasUltimoTrimestrePorcentaje = null,
          RankingUltimoAnio = null,
          TotalSkusUltimoAnio = 0
        };
      }

      // Fecha de la primera venta efectiva (> 0)
      var firstPositiveNullable = allSales.Where(v => v.Cantidad > 0).Select(v => (DateOnly?)v.Fecha).Min();
      DateOnly fechaPrimer = firstPositiveNullable ?? allSales.Min(v => v.Fecha);

      var fechaUltima = allSales.Max(v => v.Fecha);
      var cantObs = allSales.Count(v => v.Fecha >= fechaPrimer);

      // AGREGADOS POR TRIMESTRE PARA LOS DATOS EXISTENTES (sólo trimestres que tienen filas)
      var quarterSums = allSales
          .Where(v => v.Fecha >= fechaPrimer)
          .GroupBy(v => new { Year = v.Fecha.Year, Quarter = (v.Fecha.Month - 1) / 3 + 1 })
          .ToDictionary(g => (g.Key.Year, g.Key.Quarter), g => g.Sum(x => (long)x.Cantidad));

      // Determinar último trimestre completo relativo a 'today'
      var todayDateOnly = today;
      var currentQuarter = (todayDateOnly.Month - 1) / 3 + 1;
      var currentQuarterStart = new DateOnly(todayDateOnly.Year, (currentQuarter - 1) * 3 + 1, 1);
      var currentQuarterEnd = currentQuarterStart.AddMonths(3).AddDays(-1);

      int lastCompleteYear;
      int lastCompleteQuarter;

      if (todayDateOnly >= currentQuarterEnd)
      {
        lastCompleteYear = todayDateOnly.Year;
        lastCompleteQuarter = currentQuarter;
      }
      else
      {
        if (currentQuarter > 1)
        {
          lastCompleteYear = todayDateOnly.Year;
          lastCompleteQuarter = currentQuarter - 1;
        }
        else
        {
          lastCompleteYear = todayDateOnly.Year - 1;
          lastCompleteQuarter = 4;
        }
      }

      // Generar rango de trimestres desde trimestre de fechaPrimer hasta último trimestre completo
      int startQuarter = (fechaPrimer.Month - 1) / 3 + 1;
      int startIndex = fechaPrimer.Year * 4 + (startQuarter - 1);
      int endIndex = lastCompleteYear * 4 + (lastCompleteQuarter - 1);

      var fullQuarterly = new List<(int Year, int Quarter, long Total)>();
      for (int idx = startIndex; idx <= endIndex; idx++)
      {
        int y = idx / 4;
        int q = (idx % 4) + 1;
        long total = 0L;
        if (quarterSums.TryGetValue((y, q), out var t)) total = t;
        fullQuarterly.Add((Year: y, Quarter: q, Total: total));
      }

      // Calculamos mínimo incluyendo ceros (solo trimestres posteriores a la primera venta)
      ulong minTotal = 0;
      int? minYear = null, minQuarter = null;
      if (fullQuarterly.Any())
      {
        var minValue = fullQuarterly.Min(x => x.Total);
        var minCandidate = fullQuarterly
            .Where(x => x.Total == minValue)
            .OrderByDescending(x => x.Year)    // tie-break: más reciente
            .ThenByDescending(x => x.Quarter)
            .First();

        minTotal = (ulong)Math.Max(0, minCandidate.Total);
        minYear = minCandidate.Year;
        minQuarter = minCandidate.Quarter;
      }

      // Para máximo y promedio:
      // - 'quarterly' incluye todos los trimestres del rango (incluye ceros)
      // - 'quarterlyWithSales' usa solo los >0 (idéntico al comportamiento anterior para promedio)
      var quarterly = fullQuarterly.Select(f => new { Year = f.Year, Quarter = f.Quarter, Total = f.Total }).ToList();
      var quarterlyWithSales = quarterly.Where(x => x.Total > 0).ToList();

      ulong maxTotal = 0;
      int? maxYear = null, maxQuarter = null;
      if (quarterly.Any())
      {
        var maxValue = quarterly.Max(x => x.Total);
        var maxCandidate = quarterly.Where(x => x.Total == maxValue)
            .OrderByDescending(x => x.Year)
            .ThenByDescending(x => x.Quarter)
            .First();

        maxTotal = (ulong)Math.Max(0, maxCandidate.Total);
        maxYear = maxCandidate.Year;
        maxQuarter = maxCandidate.Quarter;
      }

      double avgQ = quarterlyWithSales.Any() ? quarterlyWithSales.Average(x => (double)x.Total) : 0.0;

      // Último trimestre completo y sus ventas desde fullQuarterly
      var lastQuarterYear = lastCompleteYear;
      var lastQuarterNum = lastCompleteQuarter;
      var lastQuarterLabel = $"{lastQuarterYear}-Q{lastQuarterNum}";
      var ventasUltimoTrimestreLong = fullQuarterly.FirstOrDefault(x => x.Year == lastQuarterYear && x.Quarter == lastQuarterNum).Total;
      var ventasUltimoTrimestre = (ulong)Math.Max(0, ventasUltimoTrimestreLong);

      // Ventas últimos 12 meses: coherente con TopSkusByVentas
      var desdeUltimoAnio = todayDateOnly.AddMonths(-12);
      var desdeAnioAnterior = todayDateOnly.AddMonths(-24);

      var ventasFiltro = _repo.GetAllVentas()
          .Where(v => v.Fecha >= desdeUltimoAnio && v.Fecha <= todayDateOnly && v.Cantidad > 0)
          .ToList();

      var ventasUltimoAnio = (ulong)ventasFiltro
          .Where(v => v.Sku == sku)
          .Sum(v => (long)v.Cantidad);

      var ventasPrevFiltro = _repo.GetAllVentas()
          .Where(v => v.Fecha >= desdeAnioAnterior && v.Fecha < desdeUltimoAnio && v.Cantidad > 0)
          .ToList();

      var ventasAnioAnterior = (ulong)ventasPrevFiltro
          .Where(v => v.Sku == sku)
          .Sum(v => (long)v.Cantidad);

      double? crecimientoUltimoAnio = null;
      if (ventasAnioAnterior > 0)
      {
        var raw = 100.0 * ((double)ventasUltimoAnio - (double)ventasAnioAnterior) / (double)ventasAnioAnterior;
        crecimientoUltimoAnio = Math.Round(raw, 2);
      }
      else
      {
        crecimientoUltimoAnio = null;
      }

      var qStartMonth = (lastQuarterNum - 1) * 3 + 1;
      var lastQuarterStart = new DateOnly(lastQuarterYear, qStartMonth, 1);
      var lastQuarterEndCalc = lastQuarterStart.AddMonths(3).AddDays(-1);

      var skuLastQuarter = (ulong)_repo.GetVentasBySku(sku)
          .Where(v => v.Fecha >= lastQuarterStart && v.Fecha <= lastQuarterEndCalc && v.Cantidad > 0)
          .Sum(v => (long)v.Cantidad);

      var prevQuarterYear = lastQuarterYear - 1;
      var prevQuarterStart = new DateOnly(prevQuarterYear, qStartMonth, 1);
      var prevQuarterEnd = prevQuarterStart.AddMonths(3).AddDays(-1);

      var skuPrevYearSameQuarter = (ulong)_repo.GetVentasBySku(sku)
          .Where(v => v.Fecha >= prevQuarterStart && v.Fecha <= prevQuarterEnd && v.Cantidad > 0)
          .Sum(v => (long)v.Cantidad);

      double? crecimientoUltimoTrimestreVsAnioAnterior = null;
      if (skuPrevYearSameQuarter > 0)
      {
        var rawQ = 100.0 * ((double)skuLastQuarter - (double)skuPrevYearSameQuarter) / (double)skuPrevYearSameQuarter;
        crecimientoUltimoTrimestreVsAnioAnterior = Math.Round(rawQ, 2);
      }
      else
      {
        crecimientoUltimoTrimestreVsAnioAnterior = null;
      }

      var totalUltimoAnio = (ulong)ventasFiltro.Sum(v => (long)v.Cantidad);
      double? incidenciaUltimoAnio = null;
      if (totalUltimoAnio > 0) incidenciaUltimoAnio = Math.Round((double)ventasUltimoAnio / totalUltimoAnio * 100.0, 2);

      var totalUltimoTrimestre = (ulong)_repo.GetAllVentas()
          .Where(v => v.Fecha >= lastQuarterStart && v.Fecha <= lastQuarterEndCalc && v.Cantidad > 0)
          .Sum(v => (long)v.Cantidad);

      double? incidenciaUltimoTrimestre = null;
      if (totalUltimoTrimestre > 0) incidenciaUltimoTrimestre = Math.Round((double)skuLastQuarter / totalUltimoTrimestre * 100.0, 2);

      var rankingRows = ventasFiltro
          .GroupBy(v => v.Sku)
          .Select(g => new { Sku = g.Key, Total = (ulong)g.Sum(x => x.Cantidad) })
          .OrderByDescending(x => x.Total)
          .ThenBy(x => x.Sku)
          .ToList();

      var totalSkus = _repo.GetAllVentas().Select(v => v.Sku).Distinct().Count();

      int? rank = null;
      for (var i = 0; i < rankingRows.Count; i++)
      {
        if (rankingRows[i].Sku == sku)
        {
          rank = i + 1;
          break;
        }
      }

      return new VentaSkuResumen
      {
        Sku = sku,
        FechaPrimerObservacion = fechaPrimer,
        FechaUltimaObservacion = fechaUltima,
        CantidadObservaciones = cantObs,
        MinimoVentasTrimestral = minTotal,
        TrimestreMinimoVentas = minYear.HasValue ? $"{minYear.Value}-Q{minQuarter.Value}" : null,
        MaximoVentasTrimestral = maxTotal,
        TrimestreMaximoVentas = maxYear.HasValue ? $"{maxYear.Value}-Q{maxQuarter.Value}" : null,
        PromedioVentasTrimestral = avgQ,
        VentasUltimoTrimestre = ventasUltimoTrimestre,
        UltimoTrimestre = lastQuarterLabel,
        VentasUltimoAnioCalendario = ventasUltimoAnio,
        CrecimientoVentasUltimoAnio = crecimientoUltimoAnio,
        CrecimientoVentasUltimoTrimestreVsMismoTrimestreAnioAnterior = crecimientoUltimoTrimestreVsAnioAnterior,
        IncidenciaVentasUltimoAnioPorcentaje = incidenciaUltimoAnio,
        IncidenciaVentasUltimoTrimestrePorcentaje = incidenciaUltimoTrimestre,
        RankingUltimoAnio = rank,
        TotalSkusUltimoAnio = totalSkus
      };
    }
  }
}
