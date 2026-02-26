using WebApi.Models;

namespace DataAccess.Repositories.VentasMensualesDataAccess
{
  public interface IVentasMensualesRepository
  {
    void Upsert(string sku, ushort year, byte month, ulong ventasCantidad, ushort diasConStock, string fuente);
    VentasMensuales? GetBySkuYearMonth(string sku, ushort year, byte month);
  }
}
