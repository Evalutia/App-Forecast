using System;

namespace WebApi.Controllers.StockDiario.DTOs
{
  public sealed class StockDiarioOutDto
  {
    public ulong Id { get; set; }
    public string Sku { get; set; } = null!;
    public string Fecha { get; set; } = null!;
    public uint Cantidad { get; set; }
    public string? DepositoId { get; set; }
    // Fuente and TsCarga are intentionally omitted from the public DTO
  }
}
