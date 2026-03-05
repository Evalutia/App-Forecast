using System;
using System.Collections.Generic;
using WebApi.Models;

namespace DataAccess.Repositories.StockDiarioDataAccess
{
  public interface IStockDiarioRepository
  {
    void InsertBatch(IEnumerable<StockDiario> records);
    IEnumerable<(DateOnly Fecha, uint CantidadTotal)> GetDailySumBySkuAndMonth(string sku, int year, int month);
    IEnumerable<StockDiario> GetRowsBySkuAndMonth(string sku, int year, int month, int page, int pageSize, out int total);
    IEnumerable<StockDiario> GetLatestRows(int page, int pageSize, out int total);
    IEnumerable<StockDiario> Search(string? sku, int? year, int? month, int page, int pageSize, out int total);
  }
}
