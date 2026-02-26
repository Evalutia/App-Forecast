using Microsoft.EntityFrameworkCore;
using WebApi.Data;
using WebApi.Models;

namespace DataAccess.Repositories.VentasMensualesDataAccess
{
  public class VentasMensualesRepository : IVentasMensualesRepository
  {
    private readonly EvalutiaDbContext _db;

    public VentasMensualesRepository(EvalutiaDbContext db)
    {
      _db = db;
    }

    public void Upsert(string sku, ushort year, byte month, ulong ventasCantidad, ushort diasConStock, string fuente)
    {
      using var tx = _db.Database.BeginTransaction();
      try
      {
        _db.Database.ExecuteSqlInterpolated($@"
INSERT INTO ventas_mensuales (sku, year, month, ventas_cantidad, dias_con_stock, fuente)
VALUES ({sku}, {year}, {month}, {ventasCantidad}, {diasConStock}, {fuente})
ON DUPLICATE KEY UPDATE
  ventas_cantidad = VALUES(ventas_cantidad),
  dias_con_stock = VALUES(dias_con_stock),
  fuente = IF(ventas_mensuales.fuente = 'ws', 'ws', VALUES(fuente)),
  actualizado_en = CURRENT_TIMESTAMP(6);");

        tx.Commit();
      }
      catch
      {
        tx.Rollback();
        throw;
      }
    }

    public VentasMensuales? GetBySkuYearMonth(string sku, ushort year, byte month)
    {
      return _db.VentasMensuales
                .FromSqlInterpolated($@"
SELECT *
FROM ventas_mensuales
WHERE sku = {sku}
  AND year = {year}
  AND month = {month}
LIMIT 1")
                .AsNoTracking()
                .FirstOrDefault();
    }
  }
}
