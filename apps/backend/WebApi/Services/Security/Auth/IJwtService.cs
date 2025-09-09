using WebApi.Models;

namespace Services.Security.Auth
{
  public interface IJwtService
  {
    string GenerateToken(Usuario user);
  }
}
