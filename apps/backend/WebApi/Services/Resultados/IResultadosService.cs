using WebApi.Models;

namespace Services.Resultados
{
  public interface IResultadosService
  {
    ResumenGlobalDto GetResumenGlobal();
    IReadOnlyList<SkuStockAnalysisDto> GetStockAnalysis(string? sku, string? orderBy, int page, int pageSize);
    int CountStockAnalysis(string? sku);
    IReadOnlyList<TopVentasPerdidasDto> GetTopVentasPerdidas(int top);
    StockoutDistributionDto GetStockoutDistribution();
    AbcSummaryDto GetAbcClassification();
    IReadOnlyList<VentasMensualesTrendDto> GetVentasMensualesTrend(int meses);
  }
}
