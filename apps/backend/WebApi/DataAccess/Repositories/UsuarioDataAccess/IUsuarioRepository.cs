using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using WebApi.Models;

namespace DataAccess.Repositories.UsuarioDataAccess
{
  public interface IUsuarioRepository
  {
    Usuario? GetById(int id);
    Usuario? GetByCorreo(string correo);
    (IReadOnlyList<Usuario> Items, int Total) List(int page, int pageSize, string? correo, string? rol);
    bool CorreoExists(string correo);
    int Create(Usuario u);
    void Update(Usuario u);
    bool DeleteById(int id);
  }
}
