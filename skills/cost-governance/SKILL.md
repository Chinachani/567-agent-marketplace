---
name: "cost-governance"
description: "通过预算、告警、标签和策略限制管控 Azure 成本。适用于：评估 Azure 预算健康状况、监控预算超支、查询或创建 Azure 预算、管理预算告警与覆盖率、排查缺失的 CostCenter 标签、查询允许的 VM SKU 及 Azure 区域、预检 SKU 是否受阻，以及设置成本防护栏。不适用于：规划目标预测、账单排查、定价查询、资源规格优化（rightsizing）或承诺折扣管理。"
version: "1.0.1"
license: "MIT"
metadata:
  author: Microsoft
  version: "1.0.1"
---
# Cost Governance

## Quick Reference

| Intent | Workflow | Primary tools |
|--------|----------|---------------|
| Check budget status | [Budget health](references/budget-health.md) | `list_budgets`, `forecast_costs`, `query_costs`, `list_alerts` |
| Configure a budget | [Budget setup](references/budget-setup.md) | Cost tools, `create_budget` |
| Review guardrails | [Guardrails](references/guardrails.md) | Resource Graph, `list_budgets` |

## When to Use This Skill

Use for budgets, alerts, tags, and policy.

## MCP Tools

Use cost tools for budgets; Resource Graph for guardrails. Writes need
confirmed scope, amount, thresholds, and recipients. Fallback:
[API mappings](references/tool-fallback.md).

## Workflow

1. Confirm scope and load the matching workflow.
2. Never transform MCP results in a shell or interpreter; request tool-side
   filtering or bounded follow-up queries.
3. Distinguish access failures from empty results.
4. Report gaps without implying budgets cap spend.

## Error Handling

| Error | Action |
|-------|--------|
| Access denied | Name missing permission. |
| No budget or forecast | Report unavailable data, not zero. |
| Multiple currencies | Never sum or compare across currencies. |
| Write conflict | Preserve the budget. |
| Server error | Retry once; then stop with the trace ID. |

