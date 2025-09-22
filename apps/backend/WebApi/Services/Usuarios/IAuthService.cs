using WebApi.Models;

namespace Services.Usuarios
{
  public interface IAuthService
  {
    (string Token, Usuario User) Login(Usuario cred);

    void noHayLogueado(string unMail, string unRol);
  }
}
