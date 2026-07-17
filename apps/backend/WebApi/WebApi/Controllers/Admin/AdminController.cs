using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Services.Admin;
using System;
using WebApi.Filters;
using WebApi.Models;

namespace WebApi.Controllers.Admin
{
  [ApiController]
  [Route("api/[controller]")]
  public class AdminController : ControllerBase
  {
    private readonly IAdminService _adminService;

    public AdminController(IAdminService adminService)
    {
      _adminService = adminService;
    }

    [HttpPost("recalc")]
    [Authorize(Roles = "administrador")]
    public IActionResult Recalc([FromBody] RecalcRequest request)
    {
      if (!ModelState.IsValid)
        return BadRequest(ModelState);

      DateOnly? fromDate = null;
      DateOnly? toDate = null;

      if (!string.IsNullOrWhiteSpace(request.FromDate))
      {
        if (!DateOnly.TryParse(request.FromDate, out DateOnly parsedFromDate))
          return BadRequest("Invalid fromDate format. Expected YYYY-MM-DD.");
        fromDate = parsedFromDate;
      }

      if (!string.IsNullOrWhiteSpace(request.ToDate))
      {
        if (!DateOnly.TryParse(request.ToDate, out DateOnly parsedToDate))
          return BadRequest("Invalid toDate format. Expected YYYY-MM-DD.");
        toDate = parsedToDate;
      }

      var result = _adminService.Recalc(request.Sku, fromDate, toDate);

      return Ok(new
      {
        monthsRecalculated = result.MonthsRecalculated,
        errors = result.Errors
      });
    }
  }
}
