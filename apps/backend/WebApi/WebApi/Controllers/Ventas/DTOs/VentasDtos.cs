namespace WebApi.Controllers.Ventas.DTOs
{
  // DTO para devolver ventas históricas (registro crudo)
  public sealed class VentaOutDto
  {
    public ulong Id { get; init; }
    public DateOnly Fecha { get; init; }
    public string Sku { get; init; } = string.Empty;
    public uint Cantidad { get; init; }
    public string? Fuente { get; init; }

    public VentaOutDto(WebApi.Models.VentaHistorica v)
    {
      Id = v.Id;
      Fecha = v.Fecha;
      Sku = v.Sku;
      Cantidad = v.Cantidad;
      Fuente = v.Fuente;
    }
  }

  // DTO para ventas agregadas (ej. agrupadas por mes o año)
  public sealed class VentaAgregadaOutDto
  {
    public string Sku { get; init; } = string.Empty;
    public int Anio { get; init; }
    public int? Mes { get; init; }
    public int Total { get; init; }

    public VentaAgregadaOutDto(string sku, int anio, int? mes, int total)
    {
      Sku = sku;
      Anio = anio;
      Mes = mes;
      Total = total;
    }
  }

  // DTO para autocompletar SKUs
  public sealed class SkuOutDto
  {
    public string Sku { get; init; } = string.Empty;
    public SkuOutDto(string sku) { Sku = sku; }
  }
}
