using Microsoft.EntityFrameworkCore;
using WebApi.Data;
using WebApi.Models;

namespace DataAccess.Repositories.StockDiarioDataAccess
{
  public class StockDiarioRepository : IStockDiarioRepository
  {
    private readonly EvalutiaDbContext _db;

    public StockDiarioRepository(EvalutiaDbContext db)
    {
      _db = db;
    }

    public void InsertBatch(IEnumerable<StockDiario> records)
    {
      if (records is null) throw new ArgumentNullException(nameof(records));

      var list = records.ToList();
      if (list.Count == 0) return;

      using var tx = _db.Database.BeginTransaction();
      try
      {
        foreach (var r in list)
        {
          if (string.IsNullOrWhiteSpace(r.Sku))
            throw new ArgumentException("Sku is required.");
          _db.Database.ExecuteSqlInterpolated($@"
INSERT INTO stock_diario (sku, fecha, cantidad, deposito_id, fuente, ts_carga)
VALUES ({r.Sku}, {r.Fecha}, {r.Cantidad}, {r.DepositoId}, {r.Fuente}, {r.TsCarga})
ON DUPLICATE KEY UPDATE
  cantidad = VALUES(cantidad),
  fuente = VALUES(fuente),
  ts_carga = VALUES(ts_carga);");
        }

        tx.Commit();
      }
      catch
      {
        tx.Rollback();
        throw;
      }
    }

    public IEnumerable<(DateOnly Fecha, uint CantidadTotal)> GetDailySumBySkuAndMonth(string sku, int year, int month)
    {
      if (string.IsNullOrWhiteSpace(sku)) throw new ArgumentException("sku is required", nameof(sku));
      if (year < 1) throw new ArgumentOutOfRangeException(nameof(year));
      if (month is < 1 or > 12) throw new ArgumentOutOfRangeException(nameof(month));

      var start = new DateOnly(year, month, 1);
      var end = start.AddMonths(1);

      var query =
        _db.StockDiario
          .AsNoTracking()
          .Where(x => x.Sku == sku && x.Fecha >= start && x.Fecha < end)
          .GroupBy(x => x.Fecha)
          .Select(g => new
          {
            Fecha = g.Key,
            CantidadTotal = (uint)g.Sum(x => (long)x.Cantidad)
          })
          .OrderBy(x => x.Fecha);

      return query.AsEnumerable().Select(x => (x.Fecha, x.CantidadTotal)).ToList();
    }
  }
}
