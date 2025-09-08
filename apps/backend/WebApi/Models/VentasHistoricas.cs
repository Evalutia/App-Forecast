using System;
using System.Collections.Generic;

namespace WebApi.Models;

public partial class VentaHistorica
{
  public ulong Id { get; set; }

  public DateOnly Fecha { get; set; }

  public string Sku { get; set; } = null!;

  public uint Cantidad { get; set; }

  public DateTime TsCarga { get; set; }

  public string? Fuente { get; set; }
}
