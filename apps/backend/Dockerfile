# apps/backend/Dockerfile
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# 1) Copiar la solución y TODOS los csproj (para cache de restore)
COPY ./apps/backend/WebApi/WebApi.sln ./
COPY ./apps/backend/WebApi/WebApi/WebApi.csproj ./WebApi/
COPY ./apps/backend/WebApi/DataAccess/DataAccess.csproj ./DataAccess/
COPY ./apps/backend/WebApi/Models/Models.csproj ./Models/
COPY ./apps/backend/WebApi/Services/Services.csproj ./Services/

# 2) Restore sobre la solución (trae NuGet de EF Core / Pomelo, etc.)
RUN dotnet restore ./WebApi.sln

# 3) Copiar el resto del código de la solución
COPY ./apps/backend/WebApi/ ./

# 4) Publicar el proyecto WebApi
RUN dotnet publish ./WebApi/WebApi.csproj -c Release -o /app/publish /p:UseAppHost=false

# ---------------- Runtime ----------------
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS final
WORKDIR /app
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
ENV ASPNETCORE_URLS=http://+:8080
COPY --from=build /app/publish .
EXPOSE 8080
ENTRYPOINT ["dotnet", "WebApi.dll"]
