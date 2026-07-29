using DataAccess.Repositories.PlanillaDataAccess;
using FluentAssertions;
using Microsoft.EntityFrameworkCore;
using Services.Planilla;
using WebApi.Data;
using WebApi.Models;

namespace Tests.Services
{
  public class PlanillaServiceTests
  {
    private static PlanillaService CreateService() => CreateService(out _);

    private static PlanillaService CreateService(out EvalutiaDbContext db)
    {
      var options = new DbContextOptionsBuilder<EvalutiaDbContext>()
          .UseInMemoryDatabase(Guid.NewGuid().ToString())
          .Options;
      db = new EvalutiaDbContext(options);
      return new PlanillaService(new PlanillaRepository(db));
    }

    private static PlanillaVentasCalculada Fila(string sku, int year, int month) => new()
    {
      Sku = sku,
      Year = year,
      Month = month,
      VentasCantidad = 10,
      DiasConStock = 28,
      DiasNaturalesMes = 30,
      EstadoMes = "normal",
      TicketsMes = 3
    };

    [Fact]
    public void GetVentas_CriterioFrecuenciaInvalido_LanzaArgumentException()
    {
      var service = CreateService();

      var act = () => service.GetVentas(page: 1, pageSize: 50, criterioFrecuencia: "no-existe");

      act.Should().Throw<ArgumentException>()
          .WithMessage("*no-existe*");
    }

    [Theory]
    [InlineData("historico")]
    [InlineData("promedio")]
    [InlineData("real_extrapolado")]
    public void GetVentas_CriterioFrecuenciaValido_NoLanza(string criterio)
    {
      var service = CreateService();

      var act = () => service.GetVentas(page: 1, pageSize: 50, criterioFrecuencia: criterio);

      act.Should().NotThrow();
    }

    // ── Issue #106: ventana de meses normalizada ────────────────────────────────
    // planilla_ventas_calculada solo tiene filas para meses con datos, así que la
    // lista de meses por SKU tiene largo variable (prefijo corto, hueco en el
    // medio, o cola sin mes vigente). El servicio debe devolver la MISMA ventana
    // para todos, rellenando faltantes con estadoMes="sin_datos" y valores null.

    [Fact]
    public void GetVentas_SkuConHistoriaCorta_RellenaPrefijoConSinDatos()
    {
      var service = CreateService(out var db);
      db.PlanillasVentasCalculadas.AddRange(
          Fila("SKU-VIEJO", 2026, 5),
          Fila("SKU-VIEJO", 2026, 6),
          Fila("SKU-VIEJO", 2026, 7),
          Fila("SKU-NUEVO", 2026, 7)
      );
      db.SaveChanges();

      var (items, _) = service.GetVentas(page: 1, pageSize: 50);

      items.Should().OnlyContain(i => i.Meses.Count == 3);
      var nuevo = items.Single(i => i.Sku == "SKU-NUEVO");
      nuevo.Meses.Select(m => (m.Year, m.Month))
          .Should().ContainInOrder((2026, 5), (2026, 6), (2026, 7));
      nuevo.Meses.Take(2).Should().OnlyContain(m => m.EstadoMes == "sin_datos");
      nuevo.Meses[2].EstadoMes.Should().Be("normal");
    }

    [Fact]
    public void GetVentas_SkuConHuecoEnElMedio_RellenaElHueco()
    {
      var service = CreateService(out var db);
      db.PlanillasVentasCalculadas.AddRange(
          Fila("SKU-1", 2026, 5),
          Fila("SKU-1", 2026, 7)
      );
      db.SaveChanges();

      var (items, _) = service.GetVentas(page: 1, pageSize: 50);

      var meses = items.Single().Meses;
      meses.Should().HaveCount(3);
      meses[1].Month.Should().Be(6);
      meses[1].EstadoMes.Should().Be("sin_datos");
      meses[0].EstadoMes.Should().Be("normal");
      meses[2].EstadoMes.Should().Be("normal");
    }

    [Fact]
    public void GetVentas_SkuSinMesVigente_RellenaLaCola()
    {
      // SKU discontinuado: su último mes calculado es anterior al mes de
      // referencia global. La cola debe rellenarse para que "último elemento =
      // mes vigente" valga para TODOS los SKUs (supuesto de VTA/DDSTK/RotDesEstac
      // en la tabla y el export).
      var service = CreateService(out var db);
      db.PlanillasVentasCalculadas.AddRange(
          Fila("SKU-ACTIVO", 2026, 5),
          Fila("SKU-ACTIVO", 2026, 7),
          Fila("SKU-DISCONTINUADO", 2026, 5),
          Fila("SKU-DISCONTINUADO", 2026, 6)
      );
      db.SaveChanges();

      var (items, _) = service.GetVentas(page: 1, pageSize: 50);

      var disc = items.Single(i => i.Sku == "SKU-DISCONTINUADO");
      disc.Meses.Should().HaveCount(3);
      disc.Meses[^1].Month.Should().Be(7);
      disc.Meses[^1].EstadoMes.Should().Be("sin_datos");
    }

    [Fact]
    public void GetVentas_PlaceholderSinDatos_TieneValoresNullYDiasNaturalesReales()
    {
      var service = CreateService(out var db);
      db.PlanillasVentasCalculadas.AddRange(
          Fila("SKU-1", 2026, 2),
          Fila("SKU-1", 2026, 4)
      );
      db.SaveChanges();

      var (items, _) = service.GetVentas(page: 1, pageSize: 50);

      var marzo = items.Single().Meses[1];
      marzo.Month.Should().Be(3);
      marzo.EstadoMes.Should().Be("sin_datos");
      marzo.VentasCantidad.Should().BeNull();
      marzo.DiasConStock.Should().BeNull();
      marzo.TicketsMes.Should().BeNull();
      marzo.RotacionDiariaReal.Should().BeNull();
      marzo.RotacionDiariaDesestacionalizada.Should().BeNull();
      marzo.ValorAjustado.Should().BeNull();
      marzo.CriterioFrecuencia.Should().BeNull();
      marzo.DiasNaturalesMes.Should().Be(31); // marzo real, no un 0 inventado
    }

    [Fact]
    public void GetVentas_VentanaAncladaAlMaximoGlobal_NoALaPagina()
    {
      // La página 1 (orden alfabético) contiene solo un SKU de 1 mes; la ventana
      // igual debe ser la global (3 meses), no la del contenido de la página.
      // Exactamente el bug del export del cliente (headers desde items[0]).
      var service = CreateService(out var db);
      db.PlanillasVentasCalculadas.AddRange(
          Fila("A-SKU", 2026, 6),
          Fila("Z-SKU", 2026, 5),
          Fila("Z-SKU", 2026, 6),
          Fila("Z-SKU", 2026, 7)
      );
      db.SaveChanges();

      var (items, _) = service.GetVentas(page: 1, pageSize: 1);

      items.Single().Sku.Should().Be("A-SKU");
      items.Single().Meses.Should().HaveCount(3);
      items.Single().Meses.Select(m => m.Month).Should().ContainInOrder(5, 6, 7);
    }

    [Fact]
    public void GetVentas_MesesReales_ConservanSusValores()
    {
      var service = CreateService(out var db);
      db.PlanillasVentasCalculadas.AddRange(
          Fila("SKU-1", 2026, 6),
          Fila("SKU-2", 2026, 7)
      );
      db.SaveChanges();

      var (items, _) = service.GetVentas(page: 1, pageSize: 50);

      var real = items.Single(i => i.Sku == "SKU-1").Meses[0];
      real.EstadoMes.Should().Be("normal");
      real.VentasCantidad.Should().Be(10);
      real.DiasConStock.Should().Be(28);
      real.TicketsMes.Should().Be(3);
    }

    [Fact]
    public void GetVentas_CruceDeAnio_RellenaMesesEnOrdenCalendario()
    {
      var service = CreateService(out var db);
      db.PlanillasVentasCalculadas.AddRange(
          Fila("SKU-1", 2025, 11),
          Fila("SKU-1", 2026, 2)
      );
      db.SaveChanges();

      var (items, _) = service.GetVentas(page: 1, pageSize: 50);

      var meses = items.Single().Meses;
      meses.Select(m => (m.Year, m.Month)).Should().ContainInOrder(
          (2025, 11), (2025, 12), (2026, 1), (2026, 2));
      meses[1].EstadoMes.Should().Be("sin_datos");
      meses[1].DiasNaturalesMes.Should().Be(31); // diciembre
      meses[2].EstadoMes.Should().Be("sin_datos");
    }
  }
}
