using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Filters;
using Microsoft.AspNetCore.Mvc.Authorization;  // ⬅️ IMPORTANTE

namespace WebApi.Filters
{
  [AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true, Inherited = true)]
  public sealed class AuthorizationFilter : Attribute, IAuthorizationFilter
  {
    private readonly string _role;

    public AuthorizationFilter(string role = "") => _role = role ?? string.Empty;

    public void OnAuthorization(AuthorizationFilterContext context)
    {

      var user = context.HttpContext.User;

      // 401: no autenticado
      if (user?.Identity?.IsAuthenticated != true)
      {
        context.Result = new UnauthorizedObjectResult(new ProblemDetails
        {
          Title = "No autenticado",
          Status = StatusCodes.Status401Unauthorized,
          Detail = "Falta token Bearer o es inválido."
        });
        return;
      }

      // 403: autenticado pero sin el rol requerido
      if (!string.IsNullOrWhiteSpace(_role) && !user.IsInRole(_role))
      {
        context.Result = new ObjectResult(new ProblemDetails
        {
          Title = "Prohibido",
          Status = StatusCodes.Status403Forbidden,
          Detail = $"Requiere rol '{_role}'."
        })
        { StatusCode = StatusCodes.Status403Forbidden };
      }
    }
  }
}
