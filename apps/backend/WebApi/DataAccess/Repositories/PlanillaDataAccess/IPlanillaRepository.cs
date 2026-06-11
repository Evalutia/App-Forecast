using WebApi.Models;

namespace DataAccess.Repositories.PlanillaDataAccess
{
  public interface IPlanillaRepository
  {
    (IReadOnlyList<(PlanillaVentasCalculada Fila, string? Descripcion, string? MarcaNombre, string? GeneroDescripcion, int? StockMinimo, string EstadoArticulo)> Items, int TotalSkus) GetVentas(
        int page,
        int pageSize,
        uint? marcaId,
        uint? generoId,
        string? estadoMes
    );

    (List<(uint Id, string Nombre)> Marcas, List<(uint Id, string Nombre)> Generos, int SinMarca, int SinGenero) GetFiltros();

    IReadOnlyList<PlanillaSugerencias> GetSugerencias();
  }
}
