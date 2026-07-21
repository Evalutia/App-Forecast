using DataAccess.Repositories.PlanillaDataAccess;
using FluentAssertions;
using Microsoft.EntityFrameworkCore;
using Services.Planilla;
using WebApi.Data;

namespace Tests.Services
{
  public class PlanillaServiceTests
  {
    private static PlanillaService CreateService()
    {
      var options = new DbContextOptionsBuilder<EvalutiaDbContext>()
          .UseInMemoryDatabase(Guid.NewGuid().ToString())
          .Options;
      var db = new EvalutiaDbContext(options);
      return new PlanillaService(new PlanillaRepository(db));
    }

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
  }
}
