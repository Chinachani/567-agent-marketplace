---
name: "qdrant-search-quality"
description: "诊断并优化 Qdrant 检索相关性。适用于解决“搜索结果差”、“结果不准”、“准确率或召回率低”、“匹配不相关”或“遗漏预期结果”等问题；解答“如何提升检索质量”、“Embedding 模型选型”、“是否采用混合检索或重排序 (Rerank)”等策略咨询。当因量化、模型变更或数据规模增长导致检索效果下滑时同样适用。"
version: "1.0.0"
license: "MIT"
allowed-tools:
  - Read
  - Grep
  - Glob
---
# Qdrant Search Quality

First determine whether the problem is the embedding model, Qdrant configuration, or the query strategy. Most quality issues come from the model or data, not from Qdrant itself. If search quality is low, inspect how chunks are being passed to Qdrant before tuning any parameters. Splitting mid-sentence can drop quality 30-40%.

- Start by testing with exact search to isolate the problem [Search API](https://search.qdrant.tech/md/documentation/search/search/?s=search-api)


## Diagnosis and Tuning

Isolate the source of quality issues, tune HNSW parameters, and choose the right embedding model. [Diagnosis and Tuning](diagnosis/SKILL.md)


## Search Strategies

Hybrid search, reranking, relevance feedback, and exploration APIs for improving result quality. [Search Strategies](search-strategies/SKILL.md)

