using System;
using System.Linq;
using DataAccess.Repositories.ArticuloDataAccess;
using DataAccess.Repositories.StockDiarioDataAccess;
using DataAccess.Repositories.VentasMensualesDataAccess;
using WebApi.Models;

namespace Services.Stock
{
  public class StockService : IStockService
  {
    private readonly IStockDiarioRepository _stockDiarioRepo;
    private readonly IArticuloRepository _articuloRepo;
    private readonly IVentasMensualesRepository _ventasMensualesRepo;

    public StockService(
      IStockDiarioRepository stockDiarioRepo,
      IArticuloRepository articuloRepo,
      IVentasMensualesRepository ventasMensualesRepo)
    {
      _stockDiarioRepo = stockDiarioRepo;
      _articuloRepo = articuloRepo;
      _ventasMensualesRepo = ventasMensualesRepo;
    }

    public ushort CalculateDaysWithStockForMonth(string sku, int year, int month)
    {
      if (string.IsNullOrWhiteSpace(sku))
        throw new ArgumentException("SKU is required.", nameof(sku));
      if (year < 1)
        throw new ArgumentOutOfRangeException(nameof(year));
      if (month is < 1 or > 12)
        throw new ArgumentOutOfRangeException(nameof(month));

      var dailySums = _stockDiarioRepo.GetDailySumBySkuAndMonth(sku, year, month);

      var articulo = _articuloRepo.FindBySku(sku);
      if (articulo is null)
        throw new InvalidOperationException($"Artículo con SKU '{sku}' no encontrado.");

      var stockMinimo = articulo.StockMinimo;

      var diasConStock = dailySums.Count(d => d.CantidadTotal > stockMinimo);
      return (ushort)diasConStock;
    }

    public void UpsertVentasMensualesCalculated(string sku, int year, int month, ulong ventasCantidad)
    {
      if (string.IsNullOrWhiteSpace(sku))
        throw new ArgumentException("SKU is required.", nameof(sku));
      if (year < 1)
        throw new ArgumentOutOfRangeException(nameof(year));
      if (month is < 1 or > 12)
        throw new ArgumentOutOfRangeException(nameof(month));

      var diasConStock = CalculateDaysWithStockForMonth(sku, year, month);

      _ventasMensualesRepo.Upsert(
        sku,
        (ushort)year,
        (byte)month,
        ventasCantidad,
        diasConStock,
        "calculado");
    }
  }
}
