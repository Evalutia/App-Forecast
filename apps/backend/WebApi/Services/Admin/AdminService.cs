using System;
using System.Collections.Generic;
using System.Linq;
using DataAccess.Repositories.VentaDataAccess;
using Services.Stock;

namespace Services.Admin
{
  public class AdminService : IAdminService
  {
    private readonly IStockService _stockService;
    private readonly IVentaRepository _ventaRepository;

    public AdminService(IStockService stockService, IVentaRepository ventaRepository)
    {
      _stockService = stockService;
      _ventaRepository = ventaRepository;
    }

    public RecalcResult Recalc(string? sku, DateOnly? fromDate, DateOnly? toDate)
    {
      var result = new RecalcResult();

      if (!string.IsNullOrWhiteSpace(sku))
      {
        RecalcForSku(sku, fromDate, toDate, result);
      }
      else if (fromDate.HasValue || toDate.HasValue)
      {
        var skus = _ventaRepository.DistinctSkus(filtro: null);
        foreach (var s in skus)
        {
          RecalcForSku(s, fromDate, toDate, result);
        }
      }
      else
      {
        result.Errors.Add("Provide either a SKU or a date range (fromDate/toDate).");
      }

      return result;
    }

    private void RecalcForSku(string sku, DateOnly? fromDate, DateOnly? toDate, RecalcResult result)
    {
      try
      {
        var months = GetMonthsWithinRange(fromDate, toDate);
        if (months.Count == 0)
          return;

        // Una sola consulta por SKU para todo el rango: sumamos ventas_historicas.cantidad
        // (neto de devoluciones) agrupado por year/month, en vez de recorrer mes a mes.
        var rangeStart = new DateOnly(months[0].Year, months[0].Month, 1);
        var rangeEndExclusive = new DateOnly(months[^1].Year, months[^1].Month, 1).AddMonths(1);

        var ventasPorMes = _ventaRepository.GetVentasBySku(sku)
          .Where(v => v.Fecha >= rangeStart && v.Fecha < rangeEndExclusive)
          .GroupBy(v => new { v.Fecha.Year, v.Fecha.Month })
          .Select(g => new { g.Key.Year, g.Key.Month, Total = g.Sum(v => (long)v.Cantidad) })
          .ToDictionary(x => (x.Year, x.Month), x => x.Total);

        foreach (var (year, month) in months)
        {
          try
          {
            ventasPorMes.TryGetValue((year, month), out var ventasCantidad);
            _stockService.UpsertVentasMensualesCalculated(sku, year, month, ventasCantidad);
            result.MonthsRecalculated++;
          }
          catch (Exception ex)
          {
            result.Errors.Add($"SKU {sku} {year:D4}-{month:D2}: {ex.Message}");
          }
        }
      }
      catch (Exception ex)
      {
        result.Errors.Add($"SKU {sku}: {ex.Message}");
      }
    }

    private static List<(int Year, int Month)> GetMonthsWithinRange(DateOnly? fromDate, DateOnly? toDate)
    {
      var today = DateOnly.FromDateTime(DateTime.UtcNow);
      var effectiveFrom = fromDate ?? today.AddMonths(-12);
      var effectiveTo = toDate ?? today;

      if (effectiveFrom > effectiveTo)
        return new List<(int, int)>();

      var months = new List<(int Year, int Month)>();
      var cur = new DateOnly(effectiveFrom.Year, effectiveFrom.Month, 1);
      while (cur <= effectiveTo)
      {
        months.Add((cur.Year, cur.Month));
        cur = cur.AddMonths(1);
      }

      return months;
    }
  }
}
