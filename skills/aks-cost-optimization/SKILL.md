---
name: "aks-cost-optimization"
description: "分析 AKS 高级成本效益。适用场景：“AKS NAP 就绪性”、“AKS bin packing”、“AKS 节点扩缩容瓶颈”、“AKS 缩容受阻”、“AKS 存储成本”。请勿直接作为以下场景的入口：AKS 整体成本评估或规格微调/VPA/CAS/Spot（归属于 azure-kubernetes）；支出/异常/承诺折扣（归属于 cost-analysis/cost-optimization）；故障事件（归属于 aks-troubleshooting）。"
version: "1.0.10"
license: "MIT"
metadata:
  author: Microsoft
  version: "1.0.10"
---
# AKS Cost Optimization

## When to Use This Skill

Use for advanced existing-cluster analysis requiring scheduling, placement, or
verified storage mapping. Route overall AKS cost assessments to
`azure-kubernetes`, spend/anomalies to `cost-analysis`, commitments to
`cost-optimization`, and incidents to `aks-troubleshooting` when those skills are available. When called from an overall assessment, return findings for its ranked report.

## MCP Tools

Prefer fitting Azure MCP reads. Never invent tools or use `az`/`kubectl`
without approved shell access and a target-bound context.

## Workflow/Steps

1. Bind the subscription, cluster, resource group, and kube context.
2. Route to [NAP readiness](references/aks-nap.md),
   [bin-packing](references/aks-bin-packing.md),
   [node-scaling bottlenecks](references/node-scaling-bottlenecks.md), or
   [storage optimization](references/aks-storage-optimization.md).
3. When invoked for AKS commitment context, use the
   [commitment-demand handoff](references/aks-savings-plans-reservations.md)
   and return demand evidence without benefit analysis or a transaction.
4. Keep reads non-mutating; require approval for every change.

## Error Handling

- Missing capability: analyze supplied evidence or provide a collection plan;
  mark dependent cost or commitment results unavailable.
- Evidence conflict: mark the conclusion unconfirmed.

