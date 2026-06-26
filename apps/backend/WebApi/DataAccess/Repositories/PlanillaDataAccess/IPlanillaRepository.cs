using WebApi.Models;

namespace DataAccess.Repositories.PlanillaDataAccess
{
  public interface IPlanillaRepository
  {
    (IReadOnlyList<(PlanillaVentasCalculada Fila, string? Descripcion, string? MarcaNombre, string? GeneroDescripcion, int? StockMinimo, string EstadoArticulo, string? CodigoBarras)> Items, int TotalSkus) GetVentas(
        int page,
        int pageSize,
        uint? marcaId,
        uint? generoId,
        uint? grupoId,
        string? estadoMes
    );

    (List<(uint Id, string Nombre)> Marcas, List<(uint Id, string Nombre)> Generos, List<(uint Id, string Nombre)> Grupos, int SinMarca, int SinGenero) GetFiltros(uint? grupoId);

    IReadOnlyList<PlanillaSugerencias> GetSugerencias();
  }
}
