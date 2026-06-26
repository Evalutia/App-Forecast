using System;

namespace WebApi.Models
{
    public class Grupo
    {
        public uint Id { get; set; }
        public string Descripcion { get; set; } = null!;
        public bool VisiblePlanilla { get; set; } = true;
        public bool AplicaModeloEconometrico { get; set; } = false;
        public DateTime TsCarga { get; set; }
        public DateTime? ActualizadoEn { get; set; }
    }
}
