using DataAccess.Repositories.UsuarioDataAccess;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Services.Security.Auth;
using Services.Usuarios;
using System.Text;
using WebApi.Data;

var builder = WebApplication.CreateBuilder(args);

// DbContext (Pomelo MySQL)
builder.Services.AddDbContextPool<EvalutiaDbContext>(opt => {
  var cs = builder.Configuration.GetConnectionString("EvalutiaDb");
  opt.UseMySql(cs, ServerVersion.AutoDetect(cs));
});

// JWT
builder.Services.Configure<JwtOptions>(builder.Configuration.GetSection("Jwt"));
builder.Services.AddScoped<IJwtService, JwtService>();

// DI Usuarios (sync)
builder.Services.AddScoped<IUsuarioRepository, UsuarioRepository>();
builder.Services.AddScoped<IAuthService, AuthService>();
builder.Services.AddScoped<IUsuarioService, UsuarioService>();

builder.Services.AddControllers();
// builder.Services.AddControllers(o => o.Filters.Add<ExceptionFilter>()); // <- cuando tengamos el exception filter

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// AuthN/AuthZ (si vas a proteger endpoints ahora)
var jwt = builder.Configuration.GetSection("Jwt").Get<JwtOptions>()!;
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(o =>
    {
      o.TokenValidationParameters = new()
      {
        ValidateIssuer = true,
        ValidIssuer = jwt.Issuer,
        ValidateAudience = true,
        ValidAudience = jwt.Audience,
        ValidateIssuerSigningKey = true,
        IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwt.Secret)),
        ValidateLifetime = true,
        ClockSkew = TimeSpan.FromMinutes(2)
      };
    });
builder.Services.AddAuthorization();

var app = builder.Build();
app.UseSwagger(); app.UseSwaggerUI();

app.UseHttpsRedirection();

// Habilitá esto si vas a exigir JWT en endpoints
app.UseAuthentication();
app.UseAuthorization();

app.MapControllers();
app.Run();
