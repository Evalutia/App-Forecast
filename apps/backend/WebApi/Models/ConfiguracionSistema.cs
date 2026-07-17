using System;

namespace WebApi.Models;

public partial class ConfiguracionSistema
{
  public string Clave { get; set; } = null!;

  public string Valor { get; set; } = null!;

  public string? Descripcion { get; set; }

  public DateTime ActualizadoEn { get; set; }

  public ulong? ActualizadoPor { get; set; }
}
