using DataAccess.Repositories.JobDataAccess;
using DataAccess.Repositories.PrediccionDataAccess;
using DataAccess.Repositories.UsuarioDataAccess;
using DataAccess.Repositories.VentaDataAccess;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using Microsoft.OpenApi.Models;
using Services.Jobs;
using Services.Predicciones;
using Services.Security.Auth;
using Services.Usuarios;
using Services.Ventas;
using System.Text;
using WebApi.Data;
using WebApi.Filters;

var builder = WebApplication.CreateBuilder(args);

// DbContext (Pomelo MySQL)
builder.Services.AddDbContextPool<EvalutiaDbContext>(opt =>
{
  var cs = builder.Configuration.GetConnectionString("Default");
  var serverVersion = new MySqlServerVersion(new Version(8, 0, 36));
  opt.UseMySql(cs, serverVersion, x => x.EnableRetryOnFailure(3));
});

// JWT
builder.Services.Configure<JwtOptions>(builder.Configuration.GetSection("Jwt"));
builder.Services.AddScoped<IJwtService, JwtService>();

// DI Usuarios (sync)
builder.Services.AddScoped<IUsuarioRepository, UsuarioRepository>();
builder.Services.AddScoped<IAuthService, AuthService>();
builder.Services.AddScoped<IUsuarioService, UsuarioService>();
builder.Services.AddScoped<IJobRepository, JobRepository>();
builder.Services.AddScoped<IJobService, JobService>();
builder.Services.AddScoped<IPrediccionRepository, PrediccionRepository>();
builder.Services.AddScoped<IPrediccionService, PrediccionService>();
builder.Services.AddScoped<IVentaRepository, VentaRepository>();
builder.Services.AddScoped<IVentasService, VentasService>();

// 🚨 Agregamos ExceptionFilter como filtro global
builder.Services.AddControllers(o =>
{
  o.Filters.Add<ExceptionFilter>();
});

builder.Services.AddEndpointsApiExplorer();

// 🔒 Swagger con seguridad Bearer
builder.Services.AddSwaggerGen(c =>
{
  c.SwaggerDoc("v1", new OpenApiInfo { Title = "Evalutia API", Version = "v1" });

  // Definición del esquema Bearer
  c.AddSecurityDefinition("Bearer", new OpenApiSecurityScheme
  {
    Description = "JWT en el header Authorization. Ejemplo: **Bearer eyJhbGciOi...**",
    Name = "Authorization",
    In = ParameterLocation.Header,
    Type = SecuritySchemeType.Http,
    Scheme = "bearer",
    BearerFormat = "JWT"
  });

  // Requisito global
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

// CORS
var corsPolicy = "Frontend";
builder.Services.AddCors(options =>
{
    options.AddPolicy(corsPolicy, policy =>
        policy.WithOrigins("http://localhost:5173")
              .AllowAnyHeader()
              .AllowAnyMethod()
              .AllowCredentials());
});

var app = builder.Build();
app.UseCors(corsPolicy);
app.UseSwagger();
app.UseSwaggerUI();

app.UseHttpsRedirection();

app.UseAuthentication();
app.UseAuthorization();

app.MapControllers();
app.Run();
