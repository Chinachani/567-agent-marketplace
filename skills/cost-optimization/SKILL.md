---
name: "cost-optimization"
description: "优化现有 Azure 资源配置并深度分析预留实例（Reservations）与节省计划（Savings Plans）。适用于：优化 Azure 成本、缩减云支出、调整资源规格、排查闲置资源或孤立磁盘、分析已删除虚拟机或公网 IP 仍在扣费的原因，以及评估预留实例利用率、节省计划覆盖率和承诺折扣推荐。请勿用于：成本突增分析、费用预测、价格估算、预算管理或云治理。"
version: "1.0.1"
license: "MIT"
metadata:
  author: Microsoft
  version: "1.0.1"
---
# Azure Cost Optimization

## Quick Reference

| Intent | Workflow | Primary tools |
|--------|----------|---------------|
| Reduce waste or rightsize | [Optimization](references/optimization.md) | Cost and Resource Graph tools |
| Review commitments | [Commitments](references/commitments.md) | `list_benefit_utilization`, `list_reservation_transactions`, `get_benefit_recommendations` |

## When to Use This Skill

Use for waste, rightsizing, and commitments.

## MCP Tools

Use cost and Resource Graph tools for optimization and benefit tools for
commitments. Validate queries. Fallback: [API mappings](references/tool-fallback.md).

## Workflow

1. Confirm scope, period, currency, and commitment intent.
2. Load only the matching workflow above.
3. Never transform MCP results in a shell or interpreter; request validated
   server-side projection, aggregation, or bounded follow-up queries.
4. Separate measured cost, reported savings, and qualitative opportunities.
5. Recommend changes only; do not delete, resize, purchase, or deploy resources.

## Error Handling

| Error | Action |
|-------|--------|
| Access denied | Name the scope and permission. |
| Multiple currencies | Group and report each currency separately. |
| Missing evidence | State the gap; do not invent values. |
| Server error | Retry once; then report the trace ID. |

