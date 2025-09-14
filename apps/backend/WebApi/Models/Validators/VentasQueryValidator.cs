using WebApi.Models;

namespace Models.Validators
{
  public static class VentasQueryValidator
  {
    public static void ValidarParametros(DateOnly? fechaDesde, DateOnly? fechaHasta, string? sku, string? modo)
    {
      if (fechaDesde.HasValue && fechaHasta.HasValue && fechaDesde > fechaHasta)
      {
        throw new InvalidOperationException("La fechaDesde no puede ser mayor que la fechaHasta");
      }

      if (!string.IsNullOrEmpty(sku) && sku.Length < 3)
      {
        throw new InvalidOperationException("El SKU es inválido");
      }

      if (!string.IsNullOrEmpty(modo))
      {
        var modosValidos = new[] { "historico", "agregado" };
        if (!modosValidos.Contains(modo.ToLower()))
        {
          throw new InvalidOperationException("El modo debe ser 'historico' o 'agregado'");
        }
      }
    }
  }
}
