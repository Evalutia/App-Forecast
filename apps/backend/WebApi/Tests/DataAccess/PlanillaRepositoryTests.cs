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
  }
}
