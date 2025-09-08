using System;
using System.Collections.Generic;

namespace WebApi.Models;

public partial class Usuario
{
  public ulong Id { get; set; }

  public string Correo { get; set; } = null!;

  public string HashPassword { get; set; } = null!;

  public string Rol { get; set; } = null!;

  public DateTime CreadoEn { get; set; }

  public DateTime? ActualizadoEn { get; set; }
}
