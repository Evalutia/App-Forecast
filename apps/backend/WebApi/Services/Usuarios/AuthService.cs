using DataAccess.Repositories.UsuarioDataAccess;
using Services.Security;
using Services.Security.Auth;
using WebApi.Models;

namespace Services.Usuarios
{
  public class AuthService : IAuthService
  {
    private readonly IUsuarioRepository _repo;
    private readonly IJwtService _jwt;

    public AuthService(IUsuarioRepository repo, IJwtService jwt)
    {
      _repo = repo;
      _jwt = jwt;
    }

    public (string Token, Usuario User) Login(Usuario cred)
    {
      if (cred is null)
      {
        throw new ArgumentNullException(nameof(cred));
      }

      if (string.IsNullOrWhiteSpace(cred.Correo))
      {
        throw new InvalidOperationException("Correo requerido");
      }

      if (string.IsNullOrWhiteSpace(cred.HashPassword))
      {
        throw new InvalidOperationException("Contraseña requerida");
      }

      Usuario user = _repo.GetByCorreo(cred.Correo!) ?? throw new InvalidOperationException("Credenciales inválidas");

      if (!PasswordHasher.Verify(cred.HashPassword!, user.HashPassword!))
      {
        throw new InvalidOperationException("Credenciales inválidas");
      }

      var token = _jwt.GenerateToken(user);

      return (token, user);
    }

    public void noHayLogueado(string unMail, string unRol)
    {
      if (string.IsNullOrWhiteSpace(unMail) || string.IsNullOrWhiteSpace(unRol))
      {
        throw new UnauthorizedAccessException("No hay usuario logueado");
      }
    }
  }
}
