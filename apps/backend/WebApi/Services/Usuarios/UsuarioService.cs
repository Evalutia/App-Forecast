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

    public Usuario Update(int id, Usuario cambios, string currentPasswordPlain)
    {
      ArgumentNullException.ThrowIfNull(cambios);

      var current = _repo.GetById(id)
          ?? throw new KeyNotFoundException("Usuario no encontrado");

      if (string.IsNullOrWhiteSpace(currentPasswordPlain) ||
          string.IsNullOrEmpty(current.HashPassword) ||
          !PasswordHasher.Verify(currentPasswordPlain, current.HashPassword))
      {
        throw new InvalidOperationException("Credenciales inválidas");
      }

      var nuevoRol = cambios.Rol;
      var tmp = new Usuario { Correo = current.Correo, Rol = nuevoRol };

      if (string.IsNullOrEmpty(cambios.Rol)) throw new InvalidOperationException("Rol inválido");

      var ok = new[] { "administrador", "duenoDeEmpresa" }.Contains(cambios.Rol, StringComparer.OrdinalIgnoreCase);
      if (!ok) throw new InvalidOperationException("Rol inválido");

      if (!string.Equals(current.Rol, nuevoRol, StringComparison.Ordinal))
      {
        current.Rol = nuevoRol;
        _repo.Update(current);
      }

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
