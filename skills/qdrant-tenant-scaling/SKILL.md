---
name: "qdrant-tenant-scaling"
description: "提供 Qdrant 多租户扩展与架构优化指导。适用于解答租户扩容方案、“一租户一集合”架构权衡、租户隔离策略、独立分片配置，或排查租户性能瓶颈等问题；亦可用于在多租户负载超出共享基础设施承载能力时，制定架构升级与迁移方案。"
version: "1.0.0"
license: "MIT"
---
# What to Do When Scaling Multi-Tenant Qdrant

Do not create one collection per tenant. Does not scale past a few hundred and wastes resources. One company hit the 1000 collection limit after a year of collection-per-repo and had to migrate to payload partitioning. Use a shared collection with a tenant key.

- Understand multitenancy patterns [Multitenancy](https://search.qdrant.tech/md/documentation/manage-data/multitenancy/)

Here is a short summary of the patterns:

## Number of Tenants is around 10k

Use the default multitenancy strategy via payload filtering.

Read about [Partition by payload](https://search.qdrant.tech/md/documentation/manage-data/multitenancy/?s=partition-by-payload) and [Calibrate performance](https://search.qdrant.tech/md/documentation/manage-data/multitenancy/?s=calibrate-performance) for best practices on indexing and query performance.


## Number of Tenants is around 100k and more

At this scale, the cluster may consist of several peers.
To localize tenant data and improve performance, use [custom sharding](https://search.qdrant.tech/md/documentation/operations/distributed_deployment/?s=user-defined-sharding) to assign tenants to specific shards based on tenant ID hash.
This will localize tenant requests to specific nodes instead of broadcasting them to all nodes, improving performance and reducing load on each node.

## If tenants are unevenly sized

If some tenants are much larger than others, use [tiered multitenancy](https://search.qdrant.tech/md/documentation/manage-data/multitenancy/?s=tiered-multitenancy) to promote large tenants to dedicated shards while keeping small tenants on shared shards. This optimizes resource allocation and performance for tenants of varying sizes.

## Need Strict Tenant Isolation

Use when: legal/compliance requirements demand per-tenant encryption or strict isolation beyond what payload filtering provides.

- Multiple collections may be necessary for per-tenant encryption keys
- Limit collection count and use payload filtering within each collection
- This is the exception, not the default. Only use when compliance requires it.


## What NOT to Do

- Do not create one collection per tenant without compliance justification (does not scale past hundreds)
- Do not skip `is_tenant=true` on the tenant index (kills sequential read performance)
- Do not build global HNSW for multi-tenant collections (wasteful, use `payload_m` instead)

