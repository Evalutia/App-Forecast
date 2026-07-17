using System;

namespace WebApi.Models
{
    public class StockDiario
    {
        public ulong Id { get; set; }
        public string Sku { get; set; } = null!;
        public DateOnly Fecha { get; set; }
        public uint Cantidad { get; set; }
        public string? DepositoId { get; set; }
        public string? Fuente { get; set; }
        public DateTime TsCarga { get; set; }
    }
}
