using DataAccess.Repositories.ConfiguracionDataAccess;
using FluentAssertions;
using Microsoft.EntityFrameworkCore;
using Services.Configuracion;
using WebApi.Data;

namespace Tests.Services
{
  public class ConfiguracionServiceTests
  {
    private static ConfiguracionService CreateService(out EvalutiaDbContext db)
    {
      var options = new DbContextOptionsBuilder<EvalutiaDbContext>()
          .UseInMemoryDatabase(Guid.NewGuid().ToString())
          .Options;
      db = new EvalutiaDbContext(options);
      return new ConfiguracionService(new ConfiguracionRepository(db));
    }

    [Fact]
    public void GetUmbralesTickets_SinFilasEnDb_DevuelveDefaults()
    {
      var service = CreateService(out _);

      var (bajo, alto) = service.GetUmbralesTickets();

      bajo.Should().Be(2);
      alto.Should().Be(5);
    }

    [Fact]
    public void ActualizarUmbralesTickets_ValoresValidos_PersisteYGetLosDevuelve()
    {
      var service = CreateService(out _);

      service.ActualizarUmbralesTickets(3, 8, actualizadoPor: 42);
      var (bajo, alto) = service.GetUmbralesTickets();

      bajo.Should().Be(3);
      alto.Should().Be(8);
    }

    [Fact]
    public void ActualizarUmbralesTickets_ClavesYaExistentes_ActualizaEnVezDeDuplicar()
    {
      var service = CreateService(out var db);
      service.ActualizarUmbralesTickets(3, 8, actualizadoPor: 1);

      service.ActualizarUmbralesTickets(4, 9, actualizadoPor: 2);

      db.ConfiguracionSistema.Count().Should().Be(2);
      var (bajo, alto) = service.GetUmbralesTickets();
      bajo.Should().Be(4);
      alto.Should().Be(9);
    }

    [Theory]
    [InlineData(0, 5)]
    [InlineData(2, 0)]
    [InlineData(-1, 5)]
    public void ActualizarUmbralesTickets_ValorMenorOIgualACero_LanzaInvalidOperationException(int bajo, int alto)
    {
      var service = CreateService(out _);

      var act = () => service.ActualizarUmbralesTickets(bajo, alto, actualizadoPor: null);

      act.Should().Throw<InvalidOperationException>()
          .WithMessage("*mayores a 0*");
    }

    [Fact]
    public void ActualizarUmbralesTickets_BajoMayorOIgualQueAlto_LanzaInvalidOperationException()
    {
      var service = CreateService(out _);

      var act = () => service.ActualizarUmbralesTickets(5, 5, actualizadoPor: null);

      act.Should().Throw<InvalidOperationException>()
          .WithMessage("*tickets_bajo_max debe ser menor*");
    }
  }
}
