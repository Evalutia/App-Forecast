using Microsoft.AspNetCore.Mvc;
using Services.Usuarios;
using System.Linq;
using WebApi.Controllers.Usuarios.DTOs;
using WebApi.Filters;
using WebApi.Models;

namespace WebApi.Controllers.Usuarios
{
  [ApiController]
  [Route("api/[controller]")]
  public class UsuarioController : ControllerBase
  {
    private readonly IUsuarioService _usuarioService;

    public UsuarioController(IUsuarioService usuarioService)
    {
      _usuarioService = usuarioService;
    }

    [HttpPost("crear-administrador")]
    [AuthorizationFilter("administrador")]
    public AdministradorOutDto CrearAdministrador([FromBody] CrearAdministradorDto adminDto)
    {
      var administrador = new Usuario
      {
        Correo = adminDto.Correo,
        HashPassword = adminDto.Contrasena,   
        Rol = "administrador"
      };

      var creado = _usuarioService.Add(administrador);

      return new AdministradorOutDto(creado);
    }

    [HttpDelete("borrar-administrador/{correo}")]
    [AuthorizationFilter("administrador")]
    public IActionResult BorrarAdministrador(string correo)
    {
      var user = _usuarioService.GetPorCorreo(correo);

      _usuarioService.DeletePorId((int)user.Id);

      return NoContent();
    }

    [HttpPost("crear-dueno-empresa")]
    [AuthorizationFilter("administrador")]
    public DuenoDeEmpresaOutDto CrearDuenoEmpresa([FromBody] CrearDuenoEmpresaDto dto)
    {
      var dueno = new Usuario
      {
        Correo = dto.Correo,
        HashPassword = dto.Contrasena,  
        Rol = "duenoDeEmpresa"           
      };

      Usuario creado = _usuarioService.Add(dueno);

      return new DuenoDeEmpresaOutDto(creado);
    }

    [HttpGet]
    [AuthorizationFilter("administrador")]
    public ActionResult<PagedResultDto<UsuarioOutDto>> List(
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 50,
        [FromQuery] string? correo = null,
        [FromQuery] string? rol = null)
    {
      var (items, total) = _usuarioService.List(page, pageSize, correo, rol);

      var outItems = items.Select(u => new UsuarioOutDto(
          id: (int)u.Id,
          correo: u.Correo ?? string.Empty,
          rol: u.Rol ?? string.Empty
      ));

      return Ok(new PagedResultDto<UsuarioOutDto>(outItems, page, pageSize, total));
    }

    [HttpGet("{id:int}")]
    [AuthorizationFilter("administrador")]
    public ActionResult<UsuarioOutDto> GetById([FromRoute] int id)
    {
      var u = _usuarioService.GetById(id);
      return Ok(new UsuarioOutDto(
          id: (int)u.Id,
          correo: u.Correo ?? string.Empty,
          rol: u.Rol ?? string.Empty
      ));
    }

    [HttpPut("{id:int}")]
    [AuthorizationFilter("administrador")]
    public ActionResult<UsuarioOutDto> Update([FromRoute] int id, [FromBody] UpdateUsuarioDto dto)
    {
      var cambios = new WebApi.Models.Usuario
      {
        HashPassword = dto.Contrasena,
        Rol = dto.Rol
      };

      var u = _usuarioService.Update(id, cambios);

      return Ok(new UsuarioOutDto(
          id: (int)u.Id,
          correo: u.Correo ?? string.Empty,
          rol: u.Rol ?? string.Empty
      ));
    }
  }
}
