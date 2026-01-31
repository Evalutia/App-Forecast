using System;

namespace WebApi.Models
{
    public class Articulo
    {
        public Articulo()
        {
            StockMinimo = 0;
            TsCarga = DateTime.UtcNow;
        }

        public string Sku { get; set; } = null!;
        public string? Barcode { get; set; }
        public string? Descripcion { get; set; }
        public uint? FamiliaId { get; set; }
        public string? FamiliaNombre { get; set; }
        public uint? GeneroId { get; set; }
        public string? GeneroDescripcion { get; set; }
        public uint StockMinimo { get; set; }
        public byte? FrecuenciaMensual { get; set; }
        public string? Fuente { get; set; }
        public DateTime TsCarga { get; set; }
        public DateTime? ActualizadoEn { get; set; }
    }
}
