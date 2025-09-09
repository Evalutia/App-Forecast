using System.Text.RegularExpressions;
using WebApi.Models;

namespace Models.Validators
{
  public static class UsuarioValidator
  {
    private static void EsCorreoValido(string correo)
    {
      if (!(!string.IsNullOrEmpty(correo) &&
         Regex.IsMatch(correo, @"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")))

      {
        throw new InvalidOperationException("Email inválido");
      }
      ;
    }

    private static void EsContrasenaValida(string contra)
    {
      if (string.IsNullOrEmpty(contra) ||
          contra.Length < 8 ||
          !Regex.IsMatch(contra, @"[A-Z]") ||
          !Regex.IsMatch(contra, @"[a-z]") ||
          !Regex.IsMatch(contra, @"[0-9]"))
      {
        throw new InvalidOperationException("Contraseña inválida, (8+ chars, may/min/num)");
      }
    }

    private static void EsRolValido(string rol)
    {
      var ok = new[] { "administrador", "duenoDeEmpresa" }.Contains(rol, StringComparer.OrdinalIgnoreCase);
      if (!ok) throw new InvalidOperationException("Rol inválido");
    }

    public static void Validacion(Usuario usuario)
    {
      EsCorreoValido(usuario.Correo);
      EsContrasenaValida(usuario.HashPassword);
      EsRolValido(usuario.Rol);
    }
  }
}
