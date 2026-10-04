---
name: "qdrant-monitoring"
description: "指导搭建 Qdrant 监控与可观测性体系。适用于咨询“如何监控 Qdrant”、“应关注哪些关键指标”、“Qdrant 是否健康”，排查“优化器卡死”、“内存持续增长”、“请求变慢”等性能问题，配置 Prometheus、Grafana 与健康检查，或结合指标分析定位生产环境故障。"
version: "1.0.0"
license: "MIT"
allowed-tools:
  - Read
  - Grep
  - Glob
---
# Qdrant Monitoring

Qdrant monitoring allows tracking performance and health of your deployment, and identifying issues before they become outages. First determine whether you need to set up monitoring or diagnose an active issue.

- Understand available metrics [Monitoring docs](https://search.qdrant.tech/md/documentation/operations/monitoring/)


## Monitoring Setup

Prometheus scraping, health probes, Hybrid Cloud specifics, alerting, and log centralization. [Monitoring Setup](setup/SKILL.md)


## Debugging with Metrics

Optimizer stuck, memory growth, slow requests. Using metrics to diagnose active production issues. [Debugging with Metrics](debugging/SKILL.md)

