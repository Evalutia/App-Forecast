using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Filters;
using System.Net;

namespace WebApi.Filters
{
  public class ExceptionFilter : Attribute, IExceptionFilter
  {
    public void OnException(ExceptionContext context)
    {
      var response = new ResponseDTO
      {
        EjecucionCorrecta = false
      };

      switch (context.Exception)
      {
        case ArgumentNullException:
          response.Mensaje = "Uno o más datos necesarios no fueron proporcionados.";
          context.HttpContext.Response.StatusCode = (int)HttpStatusCode.BadRequest; // 400
          break;

        case ArgumentException ex:
          response.Mensaje = "Argumento inválido: " + ex.Message;
          context.HttpContext.Response.StatusCode = (int)HttpStatusCode.BadRequest; // 400
          break;

        case UnauthorizedAccessException:
          response.Mensaje = "Acceso no autorizado.";
          context.HttpContext.Response.StatusCode = (int)HttpStatusCode.Unauthorized; // 401
          break;

        case InvalidOperationException ex:
          response.Mensaje = "Operación no válida: " + ex.Message;
          context.HttpContext.Response.StatusCode = 422; // Unprocessable Entity
          break;

        case KeyNotFoundException ex:
          response.Mensaje = ex.Message;
          context.HttpContext.Response.StatusCode = (int)HttpStatusCode.NotFound; // 404
          break;

        default:
          response.Mensaje = "Ocurrió un error inesperado. Intente nuevamente.";
          context.HttpContext.Response.StatusCode = (int)HttpStatusCode.InternalServerError; // 500
          break;
      }

      response.StatusCode = context.HttpContext.Response.StatusCode;

      context.Result = new JsonResult(response)
      {
        StatusCode = response.StatusCode
      };

      context.ExceptionHandled = true;
    }
  }
}
