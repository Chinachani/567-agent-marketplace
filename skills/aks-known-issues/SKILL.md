---
name: "aks-known-issues"
description: "仅当提示词包含准确的目录特征及其所有限定条件时，才查找已记录的 AKS 修复方案：VMCannotFitEphemeralOSDisk；NodePoolMcVersionIncompatible；'NodeImageVersion is not accepted'；包含大小、位置和可用区的 AKS SkuNotAvailable；可用区容量不足导致的 ZonalAllocationFailed；列出约束条件的 OverconstrainedAllocationRequest；嵌套的 AKS vmssCSE/CSE VMExtensionError_OutboundConnFail、VMExtensionError_K8SAPIServerConnFail 或 VMExtensionError_K8SAPIServerDNSLookupFail；或包含完整已编目内部错误或区域容量不足消息的 AllocationFailed。切勿用于配额错误、仅含代码或空包装器、一般症状、不完整特征或 AKS 之外的故障；此类情况请使用 aks-troubleshooting 或 azure-diagnostics。"
version: "1.2.1"
license: "MIT"
metadata:
  author: Microsoft
  version: "1.2.1"
---
# AKS Known Issues

## Quick Reference

| Property | Value |
|---|---|
| Best for | Exact signature plus AKS operation |
| Output | Cause, fix, and Learn citation |

Use the [catalog](references/error-code-map.md).

## When to Use This Skill

Named catalog signatures only. Generic AKS → `aks-troubleshooting`; non-AKS →
no AKS skill.

If every qualifier for a catalog row is not present, do not use this skill.
This catalog has no quota-error rows; route AKS quota incidents to
`aks-troubleshooting`.

## MCP Tools

None required. Use advertised read-only Azure tools or CLI queries.

## Workflow

1. Capture exact code, nested message, operation, and AKS resource.
2. Require every qualifier; codes are not substrings.
3. Give cause, fix, citation, and read-only verification.
4. State what ran; require explicit approval before every mutation.

## Error Handling

| Input | Response |
|---|---|
| Bare wrapper/number | Request nested signature and CSE context |
| Generic AKS | `aks-troubleshooting` |
| Non-AKS | No AKS skill |

