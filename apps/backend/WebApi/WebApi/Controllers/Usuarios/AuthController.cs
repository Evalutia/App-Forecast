using Microsoft.AspNetCore.Mvc;
using WebApi.Controllers.Usuarios.DTOs;
using WebApi.Models;
using Services.Usuarios;

namespace WebApi.Controllers.Usuarios;

[ApiController]
[Route("auth")]
public  class AuthController : ControllerBase
{
  private readonly IAuthService _auth;
  public AuthController(IAuthService auth) { _auth = auth; }

  [HttpPost("login")]
  public ActionResult<object> Login([FromBody] LoginDto dto)
  {
    var cred = new Usuario { Correo = dto.Correo, HashPassword = dto.Contrasena };

    var (token, user) = _auth.Login(cred);
    var outDto = new UsuarioOutDto((int)user.Id, user.Correo!, user.Rol!);

    return Ok(new { token, usuario = outDto });
  }

  [HttpGet("me")]
  public ActionResult<UsuarioOutDto> Me()
  {
    var idStr = User.FindFirst(System.Security.Claims.ClaimTypes.NameIdentifier)?.Value;
    var mail = User.FindFirst(System.Security.Claims.ClaimTypes.Email)?.Value;
    var rol = User.FindFirst(System.Security.Claims.ClaimTypes.Role)?.Value;

    if (string.IsNullOrWhiteSpace(mail) || string.IsNullOrWhiteSpace(rol))
      return Unauthorized();

    var id = int.TryParse(idStr, out var i) ? i : 0;
    return new UsuarioOutDto(id, mail, rol);
  }
}
