using System;
using System.Collections.Generic;

namespace WebApi.Models;

public partial class Prediccion
{
  public ulong Id { get; set; }

  public string Sku { get; set; } = null!;

  public DateOnly FechaPredicha { get; set; }

  public decimal CantidadPredicha { get; set; }

  public string Modelo { get; set; } = null!;

  public string VersionModelo { get; set; } = null!;

  public byte Horizonte { get; set; }

  public double? Rmse { get; set; }

  public double? R2 { get; set; }

  public DateTime TsGeneracion { get; set; }

  public ulong? JobId { get; set; }

  public virtual JobHistorial? Job { get; set; }
}
