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
    private static void SeedArticulo(EvalutiaDbContext db, string sku, uint stockMinimo = 0)
    {
      db.Articulos.Add(new Articulo { Sku = sku, GrupoId = 1, Estado = "activo", StockMinimo = stockMinimo, TsCarga = DateTime.UtcNow });
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

    // Issue #120 (bug 1): un articulo cuyo feed de stock_diario solo escribe
    // filas mientras tiene stock (nunca registra los dias sin stock) llega a
    // StockResumen365 con TotalDias == DiasConStock -- ETL run_calc_stock_resumen.py
    // cuenta COUNT(agg.fecha), no dias calendario. Con ese TotalDias como
    // denominador, la tasa de quiebre da 0% pase lo que pase. La planilla
    // (run_calc_planilla.py, dias_naturales_mes) usa el calendario como
    // denominador -- este mismo articulo sale "sin_stock" ahi si nunca
    // aparece con stock. El fix compara contra la ventana completa (365),
    // no contra los dias con registro.
    [Fact]
    public void GetStockAnalysis_StockoutRate_UsaVentanaCalendarioNoRegistrosConDatos()
    {
      var service = CreateService(out var db);
      SeedArticulo(db, "SKU-FEED-PARCIAL", stockMinimo: 5);
      db.StockResumen365.Add(new StockResumen365
      {
        Sku = "SKU-FEED-PARCIAL",
        TotalDias = 50,
        DiasConStock = 50,
        DiasSinStock = 0,
        Ventas365 = 20,
        TsCarga = DateTime.UtcNow,
      });
      db.SaveChanges();

      var resultados = service.GetStockAnalysis(sku: null, orderBy: null, page: 1, pageSize: 10);

      var fila = resultados.Single(r => r.Sku == "SKU-FEED-PARCIAL");
      fila.StockoutRate365.Should().BeGreaterThan(0);
    }

    // /code-review de #120: el fix de la ventana calendario, aplicado sin guarda,
    // convertia un articulo sin NINGUN dato en stock_resumen_365 (recien dado de
    // alta, aun no procesado por el ETL nocturno) en "100% quiebre" -- una falsa
    // alarma critica peor que el bug original. Sin dias observados no hay señal.
    [Fact]
    public void GetStockAnalysis_SinResumenDeStock_NoReportaQuiebreFalso()
    {
      var service = CreateService(out var db);
      SeedArticulo(db, "SKU-RECIEN-ALTA", stockMinimo: 5);
      db.SaveChanges();

      var resultados = service.GetStockAnalysis(sku: null, orderBy: null, page: 1, pageSize: 10);

      var fila = resultados.Single(r => r.Sku == "SKU-RECIEN-ALTA");
      fila.StockoutRate365.Should().Be(0);
    }

    [Fact]
    public void GetResumenGlobal_StockoutRate_UsaVentanaCalendarioNoRegistrosConDatos()
    {
      var service = CreateService(out var db);
      SeedArticulo(db, "SKU-FEED-PARCIAL", stockMinimo: 5);
      db.StockResumen365.Add(new StockResumen365
      {
        Sku = "SKU-FEED-PARCIAL",
        TotalDias = 50,
        DiasConStock = 50,
        DiasSinStock = 0,
        Ventas365 = 20,
        TsCarga = DateTime.UtcNow,
      });
      db.SaveChanges();

      var resumen = service.GetResumenGlobal();

      resumen.SkusConStockout.Should().Be(1);
      resumen.StockoutRatePromedio.Should().BeGreaterThan(0);
    }

    [Fact]
    public void GetStockoutDistribution_MismoBugQueStockAnalysis_NoCategorizaBuenoSinDatosDeQuiebre()
    {
      var service = CreateService(out var db);
      SeedArticulo(db, "SKU-FEED-PARCIAL", stockMinimo: 5);
      db.StockResumen365.Add(new StockResumen365
      {
        Sku = "SKU-FEED-PARCIAL",
        TotalDias = 50,
        DiasConStock = 50,
        DiasSinStock = 0,
        Ventas365 = 20,
        TsCarga = DateTime.UtcNow,
      });
      db.SaveChanges();

      var distribucion = service.GetStockoutDistribution();

      var item = distribucion.Items.Single(i => i.Sku == "SKU-FEED-PARCIAL");
      item.Categoria.Should().NotBe("Bueno");
    }

    // Issue #120 (bug 2): Math.Ceiling sobre una tasa por dia convertia 0.02
    // unidades/dia en "1 unidad/dia" -- 50x. La sugerencia de compra (que si
    // debe redondear hacia arriba, es una cantidad a comprar) queda intacta.
    [Fact]
    public void GetStockAnalysis_VentasPorDiaConStock365_NoRedondeaHaciaArriba()
    {
      var service = CreateService(out var db);
      SeedArticulo(db, "SKU-BAJA-ROTACION", stockMinimo: 5);
      db.StockResumen365.Add(new StockResumen365
      {
        Sku = "SKU-BAJA-ROTACION",
        TotalDias = 100,
        DiasConStock = 50,
        DiasSinStock = 50,
        Ventas365 = 1,
        TsCarga = DateTime.UtcNow,
      });
      db.SaveChanges();

      var resultados = service.GetStockAnalysis(sku: null, orderBy: null, page: 1, pageSize: 10);

      var fila = resultados.Single(r => r.Sku == "SKU-BAJA-ROTACION");
      fila.VentasPorDiaConStock365.Should().BeApproximately(0.02, 0.001);
      fila.SugerenciaCompra90.Should().Be(3); // Math.Ceiling(0.02 * 90 * 1.15) -- sin cambios
    }

    // Issue #120 (bug 3): ventas_historicas guarda una fila por SKU por dia
    // calendario, tenga o no venta real (cantidad=0 es "sin venta ese dia",
    // no ausencia de fila -- mismo invariante que el fix de #64 en
    // run_calc_planilla.py, commit ab94a09). Contar Distinct(Sku) sin filtrar
    // cantidad termina contando el catalogo entero como "activo".
    [Fact]
    public void GetVentasMensualesTrend_SkusActivos_ExcluyeFilasDeCantidadCero()
    {
      var service = CreateService(out var db);
      var hoy = DateOnly.FromDateTime(DateTime.UtcNow);
      var esteMes = new DateOnly(hoy.Year, hoy.Month, 1);

      db.VentasHistoricas.Add(new VentaHistorica { Sku = "SKU-VENDIDO", Fecha = esteMes, Cantidad = 5, TsCarga = DateTime.UtcNow });
      db.VentasHistoricas.Add(new VentaHistorica { Sku = "SKU-SIN-VENTA", Fecha = esteMes, Cantidad = 0, TsCarga = DateTime.UtcNow });
      db.SaveChanges();

      var trend = service.GetVentasMensualesTrend(3);

      var periodo = trend.Single(t => t.Periodo == $"{esteMes.Year}-{esteMes.Month:D2}");
      periodo.SkusActivos.Should().Be(1);
    }
  }
}
