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
        foreach (var (year, month) in months)
        {
          try
          {
            _stockService.UpsertVentasMensualesCalculated(sku, year, month, 0);
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
