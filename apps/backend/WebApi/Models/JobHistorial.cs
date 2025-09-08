using WebApi.Models;
using System;
using System.Collections.Generic;

namespace WebApi.Models;

public partial class JobHistorial
{
  public ulong Id { get; set; }

  public string TipoJob { get; set; } = null!;

  public string Estado { get; set; } = null!;

  public DateTime FechaInicio { get; set; }

  public DateTime? FechaFin { get; set; }

  public string? Detalle { get; set; }

  public virtual ICollection<Prediccion> Predicciones { get; set; } = new List<Prediccion>();
}
