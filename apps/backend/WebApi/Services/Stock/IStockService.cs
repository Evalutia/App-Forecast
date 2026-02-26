namespace Services.Stock
{
  public interface IStockService
  {
    ushort CalculateDaysWithStockForMonth(string sku, int year, int month);
    void UpsertVentasMensualesCalculated(string sku, int year, int month, ulong ventasCantidad);
  }
}
