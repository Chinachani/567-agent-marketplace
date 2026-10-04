---
name: "terraform-azurerm-set-diff-analyzer"
description: "分析 AzureRM Provider 的 Terraform plan JSON 输出，精准区分实际资源变更与假阳性差异（Set 类型属性仅因顺序调整导致的误报）。适用于审查 Application Gateway、Load Balancer、Firewall、Front Door、NSG 等包含 Set 类型属性的 Azure 资源，高效过滤因内部排序变动引起的虚假变更。"
version: "1.0.0"
license: "MIT"
---
# Terraform AzureRM Set Diff Analyzer

A skill to identify "false-positive diffs" in Terraform plans caused by AzureRM Provider's Set-type attributes and distinguish them from actual changes.

## When to Use

- `terraform plan` shows many changes, but you only added/removed a single element
- Application Gateway, Load Balancer, NSG, etc. show "all elements changed"
- You want to automatically filter false-positive diffs in CI/CD

## Background

Terraform's Set type compares by position rather than by key, so when adding or removing elements, all elements appear as "changed". This is a general Terraform issue, but it's particularly noticeable with AzureRM resources that heavily use Set-type attributes like Application Gateway, Load Balancer, and NSG.

These "false-positive diffs" don't actually affect the resources, but they make reviewing terraform plan output difficult.

## Prerequisites

- Python 3.8+

If Python is unavailable, install via your package manager (e.g., `apt install python3`, `brew install python3`) or from [python.org](https://www.python.org/downloads/).

## Basic Usage

```bash
# 1. Generate plan JSON output
terraform plan -out=plan.tfplan
terraform show -json plan.tfplan > plan.json

# 2. Analyze
python scripts/analyze_plan.py plan.json
```

## Troubleshooting

- **`python: command not found`**: Use `python3` instead, or install Python
- **`ModuleNotFoundError`**: Script uses only standard library; ensure Python 3.8+

## Detailed Documentation

- [scripts/README.md](scripts/README.md) - All options, output formats, exit codes, CI/CD examples
- [references/azurerm_set_attributes.md](references/azurerm_set_attributes.md) - Supported resources and attributes

