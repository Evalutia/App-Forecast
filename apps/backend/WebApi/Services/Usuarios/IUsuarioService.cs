using WebApi.Models;

namespace Services.Usuarios
{
  public interface IUsuarioService
  {
    Usuario Add(Usuario nuevo);                           
    Usuario Update(int id, Usuario cambios);              
    Usuario GetById(int id);
    Usuario GetPorCorreo(string correo);
    void DeletePorId(int id);
    (IReadOnlyList<Usuario> Items, int Total) List(int page, int pageSize, string? correo, string? rol);
  }
}
