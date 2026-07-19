using FluentAssertions;
using Microsoft.EntityFrameworkCore;
using Services.Resultados;
using WebApi.Data;
using WebApi.Models;

namespace Tests.Services
{
  public class ResultadosServiceTests
  {
    private static ResultadosService CreateService(out EvalutiaDbContext db)
    {
      var options = new DbContextOptionsBuilder<EvalutiaDbContext>()
          .UseInMemoryDatabase(Guid.NewGuid().ToString())
          .Options;
      db = new EvalutiaDbContext(options);
      return new ResultadosService(db);
    }

    // Issue #94 (code review): las filas de elegibilidad reales tienen FK a
    // articulos (articulos_elegibilidad_econometrico.sku -> articulos.sku,
    // ver infra/sql/13-articulos-elegibilidad-econometrico.sql) -- sembrar
    // el Articulo real hace que el test siga siendo valido si algun dia se
    // corre contra un provider que sí valida FKs (InMemory no lo hace).
    private static void SeedArticulo(EvalutiaDbContext db, string sku)
    {
      db.Articulos.Add(new Articulo { Sku = sku, GrupoId = 1, Estado = "activo", TsCarga = DateTime.UtcNow });
    }

    private static void SeedPrediccion(EvalutiaDbContext db, string sku, double r2, string modelo = "PROPHET")
    {
      db.Predicciones.Add(new Prediccion
      {
        Sku = sku,
        FechaPredicha = DateOnly.FromDateTime(DateTime.UtcNow),
        CantidadPredicha = 10,
        Modelo = modelo,
        VersionModelo = "v1",
        Horizonte = 1,
        R2 = r2,
        TsGeneracion = DateTime.UtcNow,
      });
    }

    [Fact]
    public void GetResumenGlobal_R2Promedio_UsaTablaDeElegibilidadNoGrupos()
    {
      // Issue #94: antes de este fix, GetSkusElegiblesModelo() leia
      // grupos.aplica_modelo_econometrico (flag muerto desde #71) en vez de
      // articulos_elegibilidad_econometrico.elegible. Este SKU es elegible
      // SOLO segun la tabla nueva -- si el servicio siguiera leyendo el
      // flag viejo (que ni se setea aca), su prediccion quedaria afuera del
      // promedio.
      var service = CreateService(out var db);
      SeedArticulo(db, "SKU-NUEVO");
      db.ArticulosElegibilidadEconometrico.Add(new ArticuloElegibilidadEconometrico { Sku = "SKU-NUEVO", Elegible = true });
      SeedPrediccion(db, "SKU-NUEVO", r2: 0.8);
      db.SaveChanges();

      var resumen = service.GetResumenGlobal();

      resumen.R2Promedio.Should().Be(0.8);
    }

    [Fact]
    public void GetResumenGlobal_R2Promedio_ExcluyeSkuNoElegible()
    {
      var service = CreateService(out var db);
      SeedArticulo(db, "SKU-NO-ELEGIBLE");
      db.ArticulosElegibilidadEconometrico.Add(new ArticuloElegibilidadEconometrico { Sku = "SKU-NO-ELEGIBLE", Elegible = false });
      SeedPrediccion(db, "SKU-NO-ELEGIBLE", r2: 0.9);
      db.SaveChanges();

      var resumen = service.GetResumenGlobal();

      resumen.R2Promedio.Should().Be(0);
    }

    [Fact]
    public void GetResumenGlobal_R2Promedio_PromediaSoloSkusElegibles()
    {
      var service = CreateService(out var db);
      SeedArticulo(db, "SKU-A");
      SeedArticulo(db, "SKU-B");
      SeedArticulo(db, "SKU-C");
      db.ArticulosElegibilidadEconometrico.AddRange(
        new ArticuloElegibilidadEconometrico { Sku = "SKU-A", Elegible = true },
        new ArticuloElegibilidadEconometrico { Sku = "SKU-B", Elegible = true },
        new ArticuloElegibilidadEconometrico { Sku = "SKU-C", Elegible = false }
      );
      SeedPrediccion(db, "SKU-A", r2: 0.4);
      SeedPrediccion(db, "SKU-B", r2: 0.6);
      SeedPrediccion(db, "SKU-C", r2: 1.0);
      db.SaveChanges();

      var resumen = service.GetResumenGlobal();

      resumen.R2Promedio.Should().Be(0.5);
    }

    [Fact]
    public void GetStockAnalysis_PronosticoProximoTrimestre_UsaTablaDeElegibilidadNoGrupos()
    {
      // Segundo consumidor real de GetSkusElegiblesModelo() -- issue #94
      // rompia este call site tambien, no solo GetResumenGlobal().
      var service = CreateService(out var db);
      var manana = DateOnly.FromDateTime(DateTime.UtcNow.AddDays(1));

      SeedArticulo(db, "SKU-ELEGIBLE");
      db.ArticulosElegibilidadEconometrico.Add(new ArticuloElegibilidadEconometrico { Sku = "SKU-ELEGIBLE", Elegible = true });
      db.Predicciones.Add(new Prediccion
      {
        Sku = "SKU-ELEGIBLE", FechaPredicha = manana, CantidadPredicha = 42,
        Modelo = "COMBINADA", VersionModelo = "v1", Horizonte = 1, TsGeneracion = DateTime.UtcNow,
      });

      SeedArticulo(db, "SKU-NO-ELEGIBLE");
      db.ArticulosElegibilidadEconometrico.Add(new ArticuloElegibilidadEconometrico { Sku = "SKU-NO-ELEGIBLE", Elegible = false });
      db.Predicciones.Add(new Prediccion
      {
        Sku = "SKU-NO-ELEGIBLE", FechaPredicha = manana, CantidadPredicha = 99,
        Modelo = "COMBINADA", VersionModelo = "v1", Horizonte = 1, TsGeneracion = DateTime.UtcNow,
      });
      db.SaveChanges();

      var resultados = service.GetStockAnalysis(sku: null, orderBy: null, page: 1, pageSize: 10);

      resultados.Single(r => r.Sku == "SKU-ELEGIBLE").PronosticoProximoTrimestre.Should().Be(42);
      resultados.Single(r => r.Sku == "SKU-NO-ELEGIBLE").PronosticoProximoTrimestre.Should().BeNull();
    }
  }
}
