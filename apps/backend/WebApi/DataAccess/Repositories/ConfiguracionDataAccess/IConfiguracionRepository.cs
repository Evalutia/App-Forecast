using WebApi.Models;

namespace DataAccess.Repositories.ConfiguracionDataAccess
{
  public interface IConfiguracionRepository
  {
    IReadOnlyList<ConfiguracionSistema> ListPorClaves(IEnumerable<string> claves);
    void UpsertMuchas(IEnumerable<(string Clave, string Valor)> valores, ulong? actualizadoPor);
  }
}
