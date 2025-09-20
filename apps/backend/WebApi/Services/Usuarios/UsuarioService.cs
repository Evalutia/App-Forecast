using DataAccess.Repositories.UsuarioDataAccess;
using Models.Validators;
using Services.Security;
using WebApi.Models;

namespace Services.Usuarios
{
  public class UsuarioService : IUsuarioService
  {
    private readonly IUsuarioRepository _repo;

    public UsuarioService(IUsuarioRepository repo)
    {
      _repo = repo;
    }

    public Usuario Add(Usuario nuevo)
    {
      if (nuevo is null)
      {
        throw new ArgumentNullException(nameof(nuevo));
      }

      UsuarioValidator.Validacion(nuevo);

      if (_repo.CorreoExists(nuevo.Correo!))
      {
        throw new InvalidOperationException($"Ya existe un usuario con el correo {nuevo.Correo}");
      }

      var hashed = PasswordHasher.Hash(nuevo.HashPassword!);

      var entity = new Usuario
      {
        Correo = nuevo.Correo,
        HashPassword = hashed,
        Rol = nuevo.Rol
      };

      var id = _repo.Create(entity);
      entity.Id = (ulong)id;

      return entity;
    }

    public Usuario Update(int id, Usuario cambios)
    {
      ArgumentNullException.ThrowIfNull(cambios);

      Usuario current = _repo.GetById(id) ?? throw new KeyNotFoundException("Usuario no encontrado");

      var tmp = new Usuario { Correo = current.Correo, HashPassword = cambios.HashPassword, Rol = cambios.Rol };

      UsuarioValidator.Validacion(tmp);

      current.HashPassword = PasswordHasher.Hash(cambios.HashPassword);
      current.Rol = cambios.Rol;

      _repo.Update(current);
      return current;
    }

    public Usuario GetById(int id)
    {
      Usuario u = _repo.GetById(id) ?? throw new KeyNotFoundException("Usuario no encontrado");
      return u;
    }

    public Usuario GetPorCorreo(string correo)
    {
      Usuario u = _repo.GetByCorreo(correo) ?? throw new KeyNotFoundException("Usuario no encontrado");
      return u;
    }

    public void DeletePorId(int id)
    {
      bool ok = _repo.DeleteById(id);
      if (!ok) throw new KeyNotFoundException("Usuario no encontrado");
    }

    public (IReadOnlyList<Usuario> Items, int Total) List(int page, int pageSize, string? correo, string? rol)
    {
      if (page < 1)
      {
        throw new InvalidOperationException("page debe ser >= 1");
      }

      if (pageSize is < 1 or > 200)
      {
        throw new InvalidOperationException("pageSize fuera de rango (1..200)");
      }

      return _repo.List(page, pageSize, correo, rol);
    }
  }
}
