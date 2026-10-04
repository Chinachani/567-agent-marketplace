---
name: "azure-local-multi-rack"
description: "规划、部署、运维及排错 Azure Local 多机架（机架级规模）部署。支持由网络交换矩阵控制器（NFC）、集群管理器（Cluster Manager）、SAN 存储及托管网络交换矩阵构建的预集成机架环境，可扩展至数百台物理机；专用于 Microsoft.NetworkCloud 和 Microsoft.ManagedNetworkFabric 控制平面。\n\n不适用于标准的 1-16 节点 Azure Local，亦不适用于机架感知型集群（将两个机架作为可用区、最多 8 节点、采用同步复制的标准规模环境）。\n\n适用场景：涉及多机架（multi-rack）、机架级（rack scale）Azure Local、汇聚机架（aggregation rack）、计算机架（compute rack）、网络交换矩阵控制器（NFC）、集群管理器、网络交换矩阵（network fabric）、隔离域（isolation domain）、az networkcloud、az networkfabric、多机架逻辑网络及多机架 Arc VM 等相关任务。"
version: "1.0.1"
license: "MIT"
metadata:
  author: Microsoft
  version: "1.0.1"
---
# Azure Local Multi-Rack

> Multi-rack is in **preview** — say so, and confirm availability from the docs before committing to a design.

## Quick Reference

| Property | Value |
| --- | --- |
| Best for | Rack-scale Azure Local: 100+ machines, preintegrated racks, SAN, managed fabric |
| Scale | Minimum four racks — one aggregation rack plus three or more compute racks |
| Providers | `Microsoft.NetworkCloud`, `Microsoft.ManagedNetworkFabric`, `Microsoft.AzureStackHCI` |
| CLI | `az networkcloud`, `az networkfabric`, `az stack-hci-vm` |
| Related skill | `azure-local` for standard 1-16 node and rack-aware deployments |

## When to Use This Skill

Use when the deployment is multi-rack / rack scale: preintegrated racks, an aggregation rack, a Network Fabric Controller, a Cluster Manager, SAN storage, or the `networkcloud` / `managednetworkfabric` CLI extensions.

Do **not** use for standard Azure Local (1-16 node hyperconverged, up to 64 disaggregated) or rack-aware clusters — hand off to the `azure-local` skill. If the scale is unclear, ask first: the two have separate, non-interchangeable procedures for the same-sounding tasks (logical networks, VM creation, NSGs).

## MCP Tools

No dedicated MCP namespace. Use generic Azure MCP tools: `mcp_azure_mcp_extension_cli_generate` (confirm `networkcloud`/`networkfabric` extensions first), `mcp_azure_mcp_monitor` (needs Log Analytics), `mcp_azure_mcp_resourcehealth` (partial; not fabric or SAN health), `mcp_azure_mcp_documentation` (multi-rack articles only — standard Azure Local pages do not apply).

Details: [cli-and-prereqs](references/cli-and-prereqs.md).

## Workflow

1. Confirm this is multi-rack, not standard Azure Local — see When to Use.
2. Plan/deploy -> [plan-and-deploy](workflows/plan-and-deploy/plan-and-deploy.md)
3. VMs, AKS, images, disks -> [workload-management](workflows/workload-management/workload-management.md)
4. Fabric, isolation domains, load balancers, NSGs -> [networking](workflows/networking/networking.md)
5. Monitoring, metrics, serial console, failures -> [operate-and-monitor](workflows/operate-and-monitor/operate-and-monitor.md)

Read the matched workflow first and use [docs-map](references/docs-map.md). Start read-only. Ask before fabric changes, isolation domain edits, VM power/delete operations, or anything touching the aggregation rack or SAN.

## Error Handling

| Scenario | Remediation |
| --- | --- |
| Scale unknown | Ask whether the deployment is multi-rack or standard before recommending procedures. |
| Standard Azure Local detected | Hand off to the `azure-local` skill; multi-rack procedures do not apply. |
| Missing CLI extension | Install per [cli-and-prereqs](references/cli-and-prereqs.md) before running commands. |
| Risky fabric or SAN change | Stop and follow [safety-rules](references/safety-rules.md). |
| Doc URL 404/redirect | Search Learn for the title, scoped to multi-rack deployments of Azure Local. |

