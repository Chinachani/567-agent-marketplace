---
name: "cost-estimation"
description: "预测 Azure 支出并估算规划中资源或工作负载的成本。\n\n适用场景：预测 Azure 费用、预估下月支出、将预测值与规划预算对比、测算虚拟机成本、对比不同存储层级或 Azure 区域价格，以及查询零售价、EA 费率卡或协议价目表。\n不适用于：已配置预算的健康度与告警检查、账单明细分析、费用突增排查、资源规格合理化（Rightsizing）调优，以及预留实例/节省计划等承诺折扣分析。"
version: "1.1.1"
license: "MIT"
metadata:
  author: Microsoft
  version: "1.1.1"
---
# Azure Cost Estimation

## Quick Reference

| Intent | Workflow | Primary tools |
|--------|----------|---------------|
| Forecast existing spend | [Cost forecast](references/cost-forecast/workflow.md) | `forecast_costs` |
| Price planned resources | [Pricing estimate](references/pricing-estimate.md) | Pricing tools |

## When to Use This Skill

Use for forecasts, pricing, and planning targets.

## MCP Tools

| Tool | Use |
|------|-----|
| `forecast_costs` | Forecast a scope. |
| `get_retail_prices` | Get public prices. |
| `start_pricesheet_download`, `get_pricesheet_status` | Get Enterprise Agreement (EA) or Microsoft Customer Agreement (MCA) prices. |

Fallback: [API mappings](references/tool-fallback.md).

## Workflow

1. Distinguish forecasts from hypothetical pricing.
2. Confirm scope, assumptions, period, region, OS, and currency.
3. Load the matching workflow and label every value type.
4. Never transform MCP results in a shell or interpreter; request tool-side
   filtering or bounded follow-up queries.

## Error Handling

| Error | Action |
|-------|--------|
| Ambiguous meter | Ask for OS, term, tier, or usage. |
| Forecast unavailable | Explain the history requirement. |
| Pricesheet pending | Honor the returned polling interval. |
| Multiple currencies | Never combine currencies. |
| Server error | Retry once; then report the trace ID. |

