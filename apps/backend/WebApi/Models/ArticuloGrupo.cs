namespace WebApi.Models
{
    // Issue #121: membresia real articulo-grupo (un articulo puede pertenecer
    // a varios grupos comerciales). articulos.grupo_id sigue existiendo como
    // "grupo principal" para los consumidores que asumen uno solo (badge de
    // la planilla); esta tabla es la fuente de verdad para filtrar.
    public class ArticuloGrupo
    {
        public string Sku { get; set; } = null!;
        public uint GrupoId { get; set; }
    }
}
