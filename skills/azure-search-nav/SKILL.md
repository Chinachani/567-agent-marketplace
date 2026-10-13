---
name: "azure-search-nav"
description: "使用 aks-search-direct-mid 语义搜索 API，为受支持的 Microsoft.ContainerService、Microsoft.Kubernetes 和 Microsoft.Compute 资源构建指向特定边栏选项卡/菜单项的 Azure 门户深层链接。适用场景：“查找在 Azure 门户中的何处执行某项操作”、“在门户中搜索某项操作”、“根据搜索查询和资源构建门户链接”。"
version: "1.0.1"
license: "MIT"
metadata:
  author: Microsoft
  version: "1.0.1"
---
# Azure Portal Search Link Builder

## Quick Reference

| Item | Value |
|------|-------|
| Script | [`references/Invoke-PortalSearchNav.ps1`](references/Invoke-PortalSearchNav.ps1) |
| Resource map | [`references/resource-types.json`](references/resource-types.json) |
| Prerequisite | `Az.Accounts` PowerShell module |
| Auth | Interactive Microsoft sign-in (`Connect-AzAccount`), or device-code with `-UseDeviceAuthentication` |

## When to Use This Skill

- User asks to find where in the Azure portal to perform an operation on a supported
  Container Service, Arc-enabled Kubernetes, or Compute resource.
- User wants a portal deep link for a specific blade/menu item.
- User provides a resource URL or ARM resource ID and a natural-language search query.

## Workflow

1. Collect **resource link** (portal URL or bare ARM resource ID) and **search query** from the user.
2. Run `references/Invoke-PortalSearchNav.ps1 -ResourceUrl '<link>' -Query '<query>'`.
3. The script signs in (browser by default; pass `-UseDeviceAuthentication` in headless/CLI
   environments), calls the search API, and prints portal deep links always rooted at
   `https://portal.azure.com`.

See [references/README.md](references/README.md) for full parameter reference and API details.

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| Resource type not enabled | `armProvider` not in `references/resource-types.json` | Confirm the type is in the enabled-provider list |
| 401 from API | Invalid token, or wrong tenant selected | Re-run and select the account with access to the target subscription's tenant |
| Empty results | No matching navigation item for the query | Try a different search term |
| `Az.Accounts` not found | Module not installed | `Install-Module Az.Accounts -Scope CurrentUser` |
| Browser sign-in fails (no window handle) | Headless/CLI environment | Re-run with `-UseDeviceAuthentication` |

