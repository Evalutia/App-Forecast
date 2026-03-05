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
        [System.ComponentModel.DataAnnotations.Schema.NotMapped]
        public string? Barcode { get; set; }
        public string? Descripcion { get; set; }
        public uint? FamiliaId { get; set; }
        public string? FamiliaNombre { get; set; }
        public uint? GeneroId { get; set; }
        public string? GeneroDescripcion { get; set; }
        public uint? SeccionId { get; set; }
        public string? SeccionNombre { get; set; }
        public uint? MarcaId { get; set; }
        public string? MarcaNombre { get; set; }
        public uint? TemporadaId { get; set; }
        public string? TemporadaNombre { get; set; }
        public DateTime? FecAlta { get; set; }
        public DateTime? FecModif { get; set; }
        public string? Comentario { get; set; }
        public string? FactDescMin { get; set; }
        public string? FactDescMax { get; set; }
        public string? DescValida { get; set; }
        public uint StockMinimo { get; set; }
        public byte? FrecuenciaMensual { get; set; }
        public string? Fuente { get; set; }
        public DateTime TsCarga { get; set; }
        public DateTime? ActualizadoEn { get; set; }
    }
}
