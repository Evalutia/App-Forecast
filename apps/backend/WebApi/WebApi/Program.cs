using DataAccess.Repositories.JobDataAccess;
using DataAccess.Repositories.PrediccionDataAccess;
using DataAccess.Repositories.UsuarioDataAccess;
using DataAccess.Repositories.VentaDataAccess;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.HttpOverrides;
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

// Forzamos Kestrel a escuchar en 0.0.0.0:${WEBAPI_PORT} si la variable está presente
var portEnv = Environment.GetEnvironmentVariable("WEBAPI_PORT") ?? builder.Configuration["WEBAPI_PORT"] ?? "8081";
if (int.TryParse(portEnv, out var webapiPort))
{
    builder.WebHost.ConfigureKestrel(options =>
    {
        options.ListenAnyIP(webapiPort);
    });
}

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

// Exception filter global
builder.Services.AddControllers(o =>
{
    o.Filters.Add<ExceptionFilter>();
});

builder.Services.AddEndpointsApiExplorer();

// Swagger + Bearer
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

// CORS - lee la variable (soporta varios orígenes separados por comas)
var corsPolicy = "Frontend";
var allowedOriginsEnv = builder.Configuration["CORS__AllowedOrigins"]
                      ?? builder.Configuration["CORS_ORIGINS"]
                      ?? "http://localhost:5173";

var origins = allowedOriginsEnv.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

builder.Services.AddCors(options =>
{
    options.AddPolicy(corsPolicy, policy =>
    {
        // Si el dev especificó "*" o un patrón para permitir todo, lo permitimos explícitamente (solo dev)
        if (origins.Length == 1 && (origins[0] == "*" || origins[0] == "http://localhost:*"))
        {
            policy.SetIsOriginAllowed(_ => true)
                  .AllowAnyHeader()
                  .AllowAnyMethod()
                  .AllowCredentials();
        }
        else
        {
            policy.WithOrigins(origins)
                  .AllowAnyHeader()
                  .AllowAnyMethod()
                  .AllowCredentials();
        }
    });
});

var app = builder.Build();

// Forwarded headers (para proxys como Caddy)
app.UseForwardedHeaders(new ForwardedHeadersOptions
{
    ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto
});

if (!app.Environment.IsDevelopment())
{
    app.UseHsts();
}

// IMPORTANT: UseCors BEFORE authentication/authorization so preflight is handled
app.UseCors(corsPolicy);
app.UseSwagger();
app.UseSwaggerUI();

app.UseHttpsRedirection();

app.UseAuthentication();
app.UseAuthorization();

app.MapControllers();
app.Run();
