using DataAccess.Repositories.PlanillaDataAccess;
using FluentAssertions;
using Microsoft.EntityFrameworkCore;
using WebApi.Data;
using WebApi.Models;

namespace Tests.DataAccess
{
  public class PlanillaRepositoryTests
  {
    private static PlanillaRepository CreateRepo(out EvalutiaDbContext db)
    {
      var options = new DbContextOptionsBuilder<EvalutiaDbContext>()
          .UseInMemoryDatabase(Guid.NewGuid().ToString())
          .Options;
      db = new EvalutiaDbContext(options);
      return new PlanillaRepository(db);
    }

    private static PlanillaVentasCalculada Fila(string sku, int year, int month, string criterio, string estadoMes = "normal") => new()
    {
      Sku = sku,
      Year = year,
      Month = month,
      VentasCantidad = 10,
      DiasConStock = 28,
      DiasNaturalesMes = 30,
      EstadoMes = estadoMes,
      TicketsMes = 3,
      CriterioFrecuencia = criterio
    };

    [Fact]
    public void GetVentas_FiltraPorCriterioFrecuenciaDelMesVigente_IgnoraMesesAnteriores()
    {
      var repo = CreateRepo(out var db);

      // SKU-1: mes vigente (el mas reciente, 2026-07) es "historico" aunque meses
      // anteriores hayan sido "real_extrapolado" -- el filtro debe mirar SOLO el
      // ultimo mes de cada SKU, no "en algun momento del año".
      db.PlanillasVentasCalculadas.AddRange(
          Fila("SKU-1", 2026, 5, "real_extrapolado"),
          Fila("SKU-1", 2026, 6, "promedio"),
          Fila("SKU-1", 2026, 7, "historico"),
          // SKU-2: mes vigente es "real_extrapolado"
          Fila("SKU-2", 2026, 6, "historico"),
          Fila("SKU-2", 2026, 7, "real_extrapolado")
      );
      db.SaveChanges();

      var (items, total) = repo.GetVentas(page: 1, pageSize: 50, marcaId: null, generoId: null, grupoId: null, estadoMes: null, criterioFrecuencia: "historico");

      total.Should().Be(1);
      items.Select(i => i.Fila.Sku).Distinct().Should().BeEquivalentTo(["SKU-1"]);
    }

    [Fact]
    public void GetVentas_SkuConUnSoloMesEnCriterioViejo_NoApareceEnFiltroDelCriterioVigente()
    {
      var repo = CreateRepo(out var db);

      db.PlanillasVentasCalculadas.AddRange(
          Fila("SKU-1", 2026, 6, "historico"),
          Fila("SKU-1", 2026, 7, "real_extrapolado")
      );
      db.SaveChanges();

      var (items, total) = repo.GetVentas(page: 1, pageSize: 50, marcaId: null, generoId: null, grupoId: null, estadoMes: null, criterioFrecuencia: "historico");

      total.Should().Be(0);
      items.Should().BeEmpty();
    }

    [Fact]
    public void GetVentas_SinFiltroDeCriterio_DevuelveTodosLosSkus()
    {
      var repo = CreateRepo(out var db);

      db.PlanillasVentasCalculadas.AddRange(
          Fila("SKU-1", 2026, 7, "historico"),
          Fila("SKU-2", 2026, 7, "real_extrapolado")
      );
      db.SaveChanges();

      var (items, total) = repo.GetVentas(page: 1, pageSize: 50, marcaId: null, generoId: null, grupoId: null, estadoMes: null, criterioFrecuencia: null);

      total.Should().Be(2);
      items.Select(i => i.Fila.Sku).Distinct().Should().BeEquivalentTo(["SKU-1", "SKU-2"]);
    }

    [Fact]
    public void GetVentas_ConCriterioFiltrado_SigueDevolviendoTodosLosMesesDelSku()
    {
      var repo = CreateRepo(out var db);

      db.PlanillasVentasCalculadas.AddRange(
          Fila("SKU-1", 2026, 6, "promedio"),
          Fila("SKU-1", 2026, 7, "historico")
      );
      db.SaveChanges();

      var (items, _) = repo.GetVentas(page: 1, pageSize: 50, marcaId: null, generoId: null, grupoId: null, estadoMes: null, criterioFrecuencia: "historico");

      // El filtro decide QUE SKUs entran, no recorta los meses de las filas devueltas
      items.Should().HaveCount(2);
      items.Select(i => i.Fila.Month).Should().BeEquivalentTo([6, 7]);
    }

    // ── Issue #121: multi-grupo ──────────────────────────────────────────────

    [Fact]
    public void GetVentas_FiltraPorGrupoSecundario_ArticuloAparece_SinDuplicarFilas()
    {
      var repo = CreateRepo(out var db);

      // SKU-1 pertenece a dos grupos reales; el "principal" (GrupoId en
      // articulos, elegido por el ETL) es el 10, pero tambien pertenece al 20.
      db.Grupos.AddRange(
          new Grupo { Id = 10, Descripcion = "GRUPO PRINCIPAL" },
          new Grupo { Id = 20, Descripcion = "GRUPO SECUNDARIO" }
      );
      db.Articulos.Add(new Articulo { Sku = "SKU-1", GrupoId = 10 });
      db.ArticuloGrupos.AddRange(
          new ArticuloGrupo { Sku = "SKU-1", GrupoId = 10 },
          new ArticuloGrupo { Sku = "SKU-1", GrupoId = 20 }
      );
      db.PlanillasVentasCalculadas.Add(Fila("SKU-1", 2026, 7, "historico"));
      db.SaveChanges();

      // Antes del fix, filtrar por el grupo 20 (secundario) no traia nada --
      // el filtro viejo comparaba contra a.GrupoId (solo el principal, 10).
      var (items, total) = repo.GetVentas(page: 1, pageSize: 50, marcaId: null, generoId: null, grupoId: 20, estadoMes: null, criterioFrecuencia: null);

      total.Should().Be(1);
      items.Should().HaveCount(1, "un JOIN directo contra articulo_grupo duplicaria esta fila una vez por membresia (mismo bug que #114)");
      items[0].Fila.Sku.Should().Be("SKU-1");
    }

    [Fact]
    public void GetVentas_FiltraPorGrupoPrincipal_SigueFuncionando()
    {
      var repo = CreateRepo(out var db);

      db.Grupos.Add(new Grupo { Id = 10, Descripcion = "GRUPO PRINCIPAL" });
      db.Articulos.Add(new Articulo { Sku = "SKU-1", GrupoId = 10 });
      db.ArticuloGrupos.Add(new ArticuloGrupo { Sku = "SKU-1", GrupoId = 10 });
      db.PlanillasVentasCalculadas.Add(Fila("SKU-1", 2026, 7, "historico"));
      db.SaveChanges();

      var (items, total) = repo.GetVentas(page: 1, pageSize: 50, marcaId: null, generoId: null, grupoId: 10, estadoMes: null, criterioFrecuencia: null);

      total.Should().Be(1);
      items.Should().HaveCount(1);
    }

    [Fact]
    public void GetVentas_FiltraPorGrupoAlQueNoPertenece_NoDevuelveNada()
    {
      var repo = CreateRepo(out var db);

      db.Grupos.AddRange(
          new Grupo { Id = 10, Descripcion = "GRUPO A" },
          new Grupo { Id = 30, Descripcion = "GRUPO B" }
      );
      db.Articulos.Add(new Articulo { Sku = "SKU-1", GrupoId = 10 });
      db.ArticuloGrupos.Add(new ArticuloGrupo { Sku = "SKU-1", GrupoId = 10 });
      db.PlanillasVentasCalculadas.Add(Fila("SKU-1", 2026, 7, "historico"));
      db.SaveChanges();

      var (items, total) = repo.GetVentas(page: 1, pageSize: 50, marcaId: null, generoId: null, grupoId: 30, estadoMes: null, criterioFrecuencia: null);

      total.Should().Be(0);
      items.Should().BeEmpty();
    }

    [Fact]
    public void GetFiltros_GrupoDondeElArticuloEsSoloSecundario_ApareceEnElDesplegable()
    {
      var repo = CreateRepo(out var db);

      // Grupo 20 nunca es "principal" de ningun articulo -- solo secundario.
      // Antes del fix, GetFiltros comparaba a.GrupoId == g.Id y este grupo
      // jamas aparecia en el desplegable aunque tuviera articulos reales.
      db.Grupos.AddRange(
          new Grupo { Id = 10, Descripcion = "GRUPO PRINCIPAL", VisiblePlanilla = true },
          new Grupo { Id = 20, Descripcion = "GRUPO SECUNDARIO", VisiblePlanilla = true }
      );
      db.Articulos.Add(new Articulo { Sku = "SKU-1", GrupoId = 10 });
      db.ArticuloGrupos.AddRange(
          new ArticuloGrupo { Sku = "SKU-1", GrupoId = 10 },
          new ArticuloGrupo { Sku = "SKU-1", GrupoId = 20 }
      );
      db.PlanillasVentasCalculadas.Add(Fila("SKU-1", 2026, 7, "historico"));
      db.SaveChanges();

      var (_, _, grupos, _, _) = repo.GetFiltros(grupoId: null);

      grupos.Select(g => g.Id).Should().BeEquivalentTo([10u, 20u]);
    }

    [Fact]
    public void GetFiltros_GrupoCatchAllNoVisible_NuncaApareceEnElDesplegable()
    {
      var repo = CreateRepo(out var db);

      db.Grupos.AddRange(
          new Grupo { Id = 10, Descripcion = "GRUPO VISIBLE", VisiblePlanilla = true },
          new Grupo { Id = 200, Descripcion = "Exportacion Web", VisiblePlanilla = false }
      );
      db.Articulos.Add(new Articulo { Sku = "SKU-1", GrupoId = 10 });
      db.ArticuloGrupos.AddRange(
          new ArticuloGrupo { Sku = "SKU-1", GrupoId = 10 },
          new ArticuloGrupo { Sku = "SKU-1", GrupoId = 200 }
      );
      db.PlanillasVentasCalculadas.Add(Fila("SKU-1", 2026, 7, "historico"));
      db.SaveChanges();

      var (_, _, grupos, _, _) = repo.GetFiltros(grupoId: null);

      grupos.Select(g => g.Id).Should().BeEquivalentTo([10u]);
    }
  }
}
