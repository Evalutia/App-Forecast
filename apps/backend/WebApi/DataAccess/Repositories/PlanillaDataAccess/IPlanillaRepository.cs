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
        string? estadoMes,
        string? criterioFrecuencia
    );

    /// <summary>
    /// Ventana global de meses presentes en planilla_ventas_calculada (min y max
    /// sobre TODA la tabla, sin filtros): ancla la normalización de #106 a datos
    /// reales, no a la fecha del sistema ni al contenido de una página.
    /// Null si la tabla está vacía.
    /// </summary>
    ((int Year, int Month) Min, (int Year, int Month) Max)? GetVentanaMeses();

    (List<(uint Id, string Nombre)> Marcas, List<(uint Id, string Nombre)> Generos, List<(uint Id, string Nombre)> Grupos, int SinMarca, int SinGenero) GetFiltros(uint? grupoId);

    IReadOnlyList<PlanillaSugerencias> GetSugerencias();
  }
}
