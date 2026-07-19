using System;

namespace WebApi.Models;

public partial class ArticuloElegibilidadEconometrico
{
  public string Sku { get; set; } = null!;

  public bool Elegible { get; set; }

  public double? R2Test { get; set; }

  public bool? Estable { get; set; }

  public byte? NFolds { get; set; }

  public ushort? MesesHistoria { get; set; }

  public DateTime EvaluadoEn { get; set; }
}
