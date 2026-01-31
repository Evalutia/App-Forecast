using System;

namespace WebApi.Models
{
    public class VentasMensuales
    {
        public ulong Id { get; set; }
        public string Sku { get; set; } = null!;
        public ushort Year { get; set; }
        public byte Month { get; set; }
        public ulong VentasCantidad { get; set; }
        public ushort DiasConStock { get; set; }
        public string Fuente { get; set; } = null!;
        public DateTime TsCarga { get; set; }
        public DateTime? ActualizadoEn { get; set; }
    }
}
