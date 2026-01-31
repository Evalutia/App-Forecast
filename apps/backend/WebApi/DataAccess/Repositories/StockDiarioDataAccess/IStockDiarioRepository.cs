using System;
using System.Collections.Generic;
using WebApi.Models;

namespace DataAccess.Repositories.StockDiarioDataAccess
{
  public interface IStockDiarioRepository
  {
    void InsertBatch(IEnumerable<StockDiario> records);
    IEnumerable<(DateOnly Fecha, uint CantidadTotal)> GetDailySumBySkuAndMonth(string sku, int year, int month);
  }
}
