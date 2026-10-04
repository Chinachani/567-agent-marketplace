---
name: "azure-kubernetes-app-deploy"
description: "用于将现有 Web 应用或 API 部署至已运行的 Azure Kubernetes Service (AKS) 集群。支持自动识别开发框架、生成 Dockerfile 和 Kubernetes 清单、针对 AKS 部署安全规则（Safeguards）进行合规校验，并执行部署与状态验证。\n\n适用场景：向现有 AKS 集群部署应用、为 Kubernetes 进行应用容器化、生成 Azure K8s 配置清单、配置 AKS CI/CD、解决 AKS 部署被安全策略拦截问题，或在 AKS 上部署 Django、Express、Spring Boot 等应用。\n\n不适用场景：创建或预配 AKS 集群（请使用 azure-kubernetes）、评估迁移到 AKS Automatic（请使用 azure-kubernetes-automatic-readiness），或部署至 Web Apps、Container Apps、Functions 等非 AKS 目标。"
version: "1.0.0"
license: "MIT"
metadata:
  author: Microsoft
  version: "1.0.0"
---
# Deploy to AKS

**Use when:** deploying a web app/API to AKS; containerizing for Kubernetes; generating manifests; AKS CI/CD; DS001–DS013 failures.

**Not for:** provisioning clusters (`azure-kubernetes`), AKS Automatic readiness (`azure-kubernetes-automatic-readiness`), non-AKS targets.

## Workflow

Requires: existing AKS cluster, `az login`, `kubectl` configured. Follow `phases/quick-deploy.md`. On failure: `references/rollback.md`.

## References

- [detection.md](./references/detection.md) — framework/port/health detection
- [safeguards.md](./references/safeguards.md) — DS001-DS013 checklist
- [workload-identity.md](./references/workload-identity.md) — Workload Identity setup
- [rollback.md](./references/rollback.md) — recovery procedures
- [base-images.md](./references/base-images.md) — base image policy and `<LATEST_STABLE_*>` resolution

## Knowledge Packs

Load `knowledge-packs/frameworks/<framework>.md` per detected framework. Available: `spring-boot`, `express`, `nextjs`, `fastapi`, `django`, `nestjs`, `aspnet-core`, `go`, `flask`

## Templates

`templates/` (dockerfiles/, k8s/, github-actions/, mermaid/).

