using DataAccess.Repositories.VentaDataAccess;
using FluentAssertions;
using Moq;
using Services.Admin;
using Services.Stock;
using WebApi.Models;

namespace Tests.Services
{
  public class AdminServiceTests
  {
    private static (AdminService Service, Mock<IStockService> StockServiceMock, List<(string Sku, int Year, int Month, long VentasCantidad)> Calls)
      CreateService(IEnumerable<VentaHistorica> ventas)
    {
      var ventaRepoMock = new Mock<IVentaRepository>();
      ventaRepoMock
        .Setup(r => r.GetVentasBySku(It.IsAny<string>()))
        .Returns((string sku) => ventas.Where(v => v.Sku == sku).AsQueryable());

      var calls = new List<(string Sku, int Year, int Month, long VentasCantidad)>();
      var stockServiceMock = new Mock<IStockService>();
      stockServiceMock
        .Setup(s => s.UpsertVentasMensualesCalculated(It.IsAny<string>(), It.IsAny<int>(), It.IsAny<int>(), It.IsAny<long>()))
        .Callback<string, int, int, long>((sku, year, month, cantidad) => calls.Add((sku, year, month, cantidad)));

      var service = new AdminService(stockServiceMock.Object, ventaRepoMock.Object);
      return (service, stockServiceMock, calls);
    }

    [Fact]
    public void Recalc_SkuConVentasYDevoluciones_PasaLaSumaRealDeVentasHistoricasAlUpsert()
    {
      // "SKU1" vendió 10 + 5 unidades en marzo y tuvo una devolución de 2 (cantidad negativa),
      // más una venta en abril que no debe entrar en el cálculo de marzo.
      var ventas = new List<VentaHistorica>
      {
        new() { Sku = "SKU1", Fecha = new DateOnly(2026, 3, 5), Cantidad = 10 },
        new() { Sku = "SKU1", Fecha = new DateOnly(2026, 3, 20), Cantidad = 5 },
        new() { Sku = "SKU1", Fecha = new DateOnly(2026, 3, 25), Cantidad = -2 },
        new() { Sku = "SKU1", Fecha = new DateOnly(2026, 4, 1), Cantidad = 100 },
      };
      var (service, _, calls) = CreateService(ventas);

      service.Recalc("SKU1", new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 31));

      calls.Should().ContainSingle();
      var call = calls[0];
      call.Sku.Should().Be("SKU1");
      call.Year.Should().Be(2026);
      call.Month.Should().Be(3);
      call.VentasCantidad.Should().Be(13); // 10 + 5 - 2, no 0
    }

    [Fact]
    public void Recalc_NuncaPasaUnValorFijoIndependienteDeLosDatosCrudos()
    {
      // Regresión directa del bug del issue #118: el recálculo pasaba un 0 literal
      // sin importar qué hubiera en ventas_historicas. Este test corre el mismo
      // recálculo sobre dos meses con ventas reales distintas y exige que el valor
      // pasado a UpsertVentasMensualesCalculated siga a los datos, no sea constante.
      var ventas = new List<VentaHistorica>
      {
        new() { Sku = "SKU1", Fecha = new DateOnly(2026, 3, 10), Cantidad = 7 },
        new() { Sku = "SKU1", Fecha = new DateOnly(2026, 4, 10), Cantidad = 21 },
      };
      var (service, _, calls) = CreateService(ventas);

      service.Recalc("SKU1", new DateOnly(2026, 3, 1), new DateOnly(2026, 4, 30));

      calls.Should().HaveCount(2);
      calls.Should().NotContain(c => c.VentasCantidad == 0);
      calls.Single(c => c.Month == 3).VentasCantidad.Should().Be(7);
      calls.Single(c => c.Month == 4).VentasCantidad.Should().Be(21);
    }

    [Fact]
    public void Recalc_SkuSinVentasEnElMes_PasaCeroRealNoUnErrorNiUnValorFalso()
    {
      var ventas = new List<VentaHistorica>();
      var (service, _, calls) = CreateService(ventas);

      var result = service.Recalc("SKU-SIN-VENTAS", new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 31));

      result.Errors.Should().BeEmpty();
      calls.Should().ContainSingle();
      calls[0].VentasCantidad.Should().Be(0);
    }
  }
}
