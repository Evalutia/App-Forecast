using System;

namespace WebApi.Models
{
    public class VentaHistorica
    {
        public ulong Id { get; set; }
        public DateOnly Fecha { get; set; }
        public string Sku { get; set; } = null!;
        public uint Cantidad { get; set; }
        public DateTime TsCarga { get; set; }
        public string? Fuente { get; set; }
        public string? Barcode { get; set; }
        public string? DescripcionArticulo { get; set; }
        public uint? FamiliaId { get; set; }
        public string? FamiliaNombre { get; set; }
        public uint? GeneroId { get; set; }
        public string? GeneroDescripcion { get; set; }
        public uint StockMinimo { get; set; }
        public byte? FrecuenciaMensual { get; set; }
    }
}
