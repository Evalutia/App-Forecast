using Microsoft.Extensions.Options;
using Microsoft.IdentityModel.Tokens;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using WebApi.Models;

namespace Services.Security.Auth
{
  public class JwtService(IOptions<JwtOptions> opt) : IJwtService
  {
    private readonly JwtOptions _opt = opt.Value;

    public string GenerateToken(Usuario user)
    {
      var claims = new[]
      {
            new Claim(JwtRegisteredClaimNames.Sub, user.Id.ToString()),
            new Claim(ClaimTypes.Email, user.Correo!),
            new Claim(ClaimTypes.Role,  user.Rol!)
        };

      var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(_opt.Secret));
      var creds = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

      var jwt = new JwtSecurityToken(_opt.Issuer, _opt.Audience, claims,
          expires: DateTime.UtcNow.AddHours(_opt.ExpiresHours),
          signingCredentials: creds);

      return new JwtSecurityTokenHandler().WriteToken(jwt);
    }
  }
}
