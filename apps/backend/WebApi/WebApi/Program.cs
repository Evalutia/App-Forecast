using DataAccess.Repositories.JobDataAccess;
using DataAccess.Repositories.PrediccionDataAccess;
using DataAccess.Repositories.UsuarioDataAccess;
using DataAccess.Repositories.JobDataAccess;
using DataAccess.Repositories.VentaDataAccess;   // 👈 agregado
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using Microsoft.OpenApi.Models;
using Services.Jobs;
using Services.Predicciones;
using Services.Security.Auth;
using Services.Usuarios;
using Services.Jobs;
using Services.Ventas;                           // 👈 agregado
using System.Text;
using WebApi.Data;
using Microsoft.OpenApi.Models;
using DataAccess.Repositories.JobDataAccess;
using Services.Jobs;
using DataAccess.Repositories.JobDataAccess;
using Services.Jobs;
builder.Services.AddDbContextPool<EvalutiaDbContext>(opt =>
{
    var cs = builder.Configuration.GetConnectionString("Default");
    var serverVersion = new MySqlServerVersion(new Version(8, 0, 36));
    opt.UseMySql(cs, serverVersion, x => x.EnableRetryOnFailure(3));
var builder = WebApplication.CreateBuilder(args);

// DbContext (Pomelo MySQL)
builder.Services.AddDbContextPool<EvalutiaDbContext>(opt => {
  var cs = builder.Configuration.GetConnectionString("EvalutiaDb");
  opt.UseMySql(cs, ServerVersion.AutoDetect(cs));
});

// JWT
builder.Services.Configure<JwtOptions>(builder.Configuration.GetSection("Jwt"));
builder.Services.AddScoped<IJwtService, JwtService>();

// DI Usuarios
builder.Services.AddScoped<IUsuarioRepository, UsuarioRepository>();
builder.Services.AddScoped<IAuthService, AuthService>();
builder.Services.AddScoped<IUsuarioService, UsuarioService>();

// DI Jobs
builder.Services.AddScoped<IJobRepository, JobRepository>();
builder.Services.AddScoped<IJobService, JobService>();
builder.Services.AddScoped<IPrediccionRepository, PrediccionRepository>();
builder.Services.AddScoped<IPrediccionService, PrediccionService>();


// DI Ventas 👇
builder.Services.AddScoped<IVentaRepository, VentaRepository>();
builder.Services.AddScoped<IVentasService, VentasService>();

builder.Services.AddControllers();
// builder.Services.AddControllers(o => o.Filters.Add<ExceptionFilter>()); // <- cuando tengas ExceptionFilter

builder.Services.AddEndpointsApiExplorer();

// 🔒 Swagger con seguridad Bearer
builder.Services.AddSwaggerGen(c =>
{
  c.SwaggerDoc("v1", new OpenApiInfo { Title = "Evalutia API", Version = "v1" });

  c.AddSecurityDefinition("Bearer", new OpenApiSecurityScheme
  {
    Description = "JWT en el header Authorization. Ejemplo: **Bearer eyJhbGciOi...**",
    Name = "Authorization",
    In = ParameterLocation.Header,
    Type = SecuritySchemeType.Http,
    Scheme = "bearer",
    BearerFormat = "JWT"
  });

  c.AddSecurityRequirement(new OpenApiSecurityRequirement
    {
        {
            new OpenApiSecurityScheme
            {
                Reference = new OpenApiReference
                {
                    Type = ReferenceType.SecurityScheme,
                    Id = "Bearer"
                }
            },
            Array.Empty<string>()
        }
    });
});

// AuthN/AuthZ
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
app.UseSwagger();
app.UseSwaggerUI();

app.UseHttpsRedirection();

app.UseAuthentication();
app.UseAuthorization();

app.MapControllers();
app.Run();
