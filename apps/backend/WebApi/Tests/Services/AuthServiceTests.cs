using DataAccess.Repositories.UsuarioDataAccess;
using FluentAssertions;
using Microsoft.EntityFrameworkCore;
using Moq;
using Services.Security;
using Services.Security.Auth;
using Services.Usuarios;
using WebApi.Data;
using WebApi.Models;

namespace Tests.Services
{
  public class AuthServiceTests
  {
    private static (AuthService Service, EvalutiaDbContext Db, Mock<IJwtService> JwtMock) CreateService()
    {
      var options = new DbContextOptionsBuilder<EvalutiaDbContext>()
          .UseInMemoryDatabase(Guid.NewGuid().ToString())
          .Options;
      var db = new EvalutiaDbContext(options);
      var jwtMock = new Mock<IJwtService>();
      var service = new AuthService(new UsuarioRepository(db), jwtMock.Object);
      return (service, db, jwtMock);
    }

    [Fact]
    public void Login_CredencialesValidas_DevuelveTokenGeneradoPorJwtService()
    {
      var (service, db, jwtMock) = CreateService();
      db.Usuarios.Add(new Usuario
      {
        Correo = "user@evalutia.com",
        HashPassword = PasswordHasher.Hash("clave-secreta"),
        Rol = "administrador",
        CreadoEn = DateTime.UtcNow
      });
      db.SaveChanges();
      jwtMock.Setup(j => j.GenerateToken(It.IsAny<Usuario>())).Returns("token-fake");

      var (token, user) = service.Login(new Usuario { Correo = "user@evalutia.com", HashPassword = "clave-secreta" });

      token.Should().Be("token-fake");
      user.Correo.Should().Be("user@evalutia.com");
      jwtMock.Verify(j => j.GenerateToken(It.Is<Usuario>(u => u.Correo == "user@evalutia.com")), Times.Once);
    }

    [Fact]
    public void Login_ContraseñaIncorrecta_LanzaCredencialesInvalidas()
    {
      var (service, db, _) = CreateService();
      db.Usuarios.Add(new Usuario
      {
        Correo = "user@evalutia.com",
        HashPassword = PasswordHasher.Hash("clave-correcta"),
        Rol = "administrador",
        CreadoEn = DateTime.UtcNow
      });
      db.SaveChanges();

      var act = () => service.Login(new Usuario { Correo = "user@evalutia.com", HashPassword = "clave-incorrecta" });

      act.Should().Throw<InvalidOperationException>().WithMessage("Credenciales inválidas");
    }

    [Fact]
    public void Login_CorreoNoExiste_LanzaCredencialesInvalidas()
    {
      var (service, _, _) = CreateService();

      var act = () => service.Login(new Usuario { Correo = "no-existe@evalutia.com", HashPassword = "cualquiera" });

      act.Should().Throw<InvalidOperationException>().WithMessage("Credenciales inválidas");
    }

    [Fact]
    public void Login_CorreoVacio_LanzaCorreoRequerido()
    {
      var (service, _, _) = CreateService();

      var act = () => service.Login(new Usuario { Correo = "", HashPassword = "clave" });

      act.Should().Throw<InvalidOperationException>().WithMessage("Correo requerido");
    }

    [Fact]
    public void Login_CredencialesNulas_LanzaArgumentNullException()
    {
      var (service, _, _) = CreateService();

      var act = () => service.Login(null!);

      act.Should().Throw<ArgumentNullException>();
    }
  }
}
