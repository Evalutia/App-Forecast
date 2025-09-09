namespace WebApi.Controllers.Usuarios.DTOs
{
  public sealed class LoginDto
  {
    public string Correo { get; set; } = string.Empty;
    public string Contrasena { get; set; } = string.Empty;
  }

  public sealed class CrearAdministradorDto
  {
    public string Correo { get; set; } = string.Empty;
    public string Contrasena { get; set; } = string.Empty;
  }

  public sealed class CrearDuenoEmpresaDto
  {
    public string Correo { get; set; } = string.Empty;
    public string Contrasena { get; set; } = string.Empty;
  }

  public sealed class UpdateUsuarioDto
  {
    public string? Contrasena { get; set; }
    public string? Rol { get; set; }
  }

  public sealed class UsuarioOutDto
  {
    public int Id { get; init; }
    public string Correo { get; init; } = string.Empty;
    public string Rol { get; init; } = string.Empty;
    public UsuarioOutDto(int id, string correo, string rol) { Id = id; Correo = correo; Rol = rol; }
  }

  public sealed class AdministradorOutDto
  {
    public int Id { get; init; }
    public string Correo { get; init; } = string.Empty;
    public string Rol { get; init; } = "administrador";
    public AdministradorOutDto(WebApi.Models.Usuario u) { Id = (int)u.Id; Correo = u.Correo!; Rol = u.Rol!; }
  }

  public sealed class DuenoDeEmpresaOutDto
  {
    public int Id { get; init; }
    public string Correo { get; init; } = string.Empty;
    public string Rol { get; init; } = "duenoDeEmpresa";
    public DuenoDeEmpresaOutDto(WebApi.Models.Usuario u) { Id = (int)u.Id; Correo = u.Correo!; Rol = u.Rol!; }
  }

  public sealed class PagedResultDto<T>
  {
    public IEnumerable<T> Items { get; init; } = Enumerable.Empty<T>();
    public int Page { get; init; }
    public int PageSize { get; init; }
    public int Total { get; init; }
    public PagedResultDto(IEnumerable<T> items, int page, int pageSize, int total)
    { Items = items; Page = page; PageSize = pageSize; Total = total; }
  }
}
