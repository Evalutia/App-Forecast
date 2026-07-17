using WebApi.Data;
using WebApi.Models;

namespace DataAccess.Repositories.ConfiguracionDataAccess
{
  public class ConfiguracionRepository : IConfiguracionRepository
  {
    private readonly EvalutiaDbContext _db;
    public ConfiguracionRepository(EvalutiaDbContext db) { _db = db; }

    public IReadOnlyList<ConfiguracionSistema> ListPorClaves(IEnumerable<string> claves)
    {
      return _db.ConfiguracionSistema.Where(c => claves.Contains(c.Clave)).ToList();
    }

    public void UpsertMuchas(IEnumerable<(string Clave, string Valor)> valores, ulong? actualizadoPor)
    {
      var claves = valores.Select(v => v.Clave).ToList();
      var existentes = _db.ConfiguracionSistema
        .Where(c => claves.Contains(c.Clave))
        .ToDictionary(c => c.Clave);

      foreach (var (clave, valor) in valores)
      {
        if (existentes.TryGetValue(clave, out var existente))
        {
          existente.Valor = valor;
          existente.ActualizadoPor = actualizadoPor;
        }
        else
        {
          _db.ConfiguracionSistema.Add(new ConfiguracionSistema
          {
            Clave = clave,
            Valor = valor,
            ActualizadoPor = actualizadoPor
          });
        }
      }

      _db.SaveChanges();
    }
  }
}
