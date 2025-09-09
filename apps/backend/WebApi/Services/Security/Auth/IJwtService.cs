using WebApi.Models;

namespace Services.Security.Auth
{
  internal interface IJwtService
  {
    string GenerateToken(Usuario user);
  }
}
