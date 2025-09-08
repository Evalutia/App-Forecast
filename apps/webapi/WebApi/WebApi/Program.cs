using Microsoft.EntityFrameworkCore;
using WebApi.Data;

var builder = WebApplication.CreateBuilder(args);

// Swagger (Swashbuckle)
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// DbContext (Pomelo MySQL)
var conn = builder.Configuration.GetConnectionString("EvalutiaDb");
builder.Services.AddDbContext<EvalutiaDbContext>(options =>
{
  var serverVersion = ServerVersion.AutoDetect(conn);
  options.UseMySql(conn, serverVersion, mySql =>
  {
    mySql.EnableRetryOnFailure();
  });
});

var app = builder.Build();

// Swagger en Development
if (app.Environment.IsDevelopment())
{
  app.UseSwagger();
  app.UseSwaggerUI();
}

app.UseHttpsRedirection();

// Endpoint de ejemplo con tu DB
app.MapGet("/api/ventas", async (EvalutiaDbContext db) =>
    await db.VentasHistoricas.ToListAsync()
);

app.Run();
