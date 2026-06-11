# ADR-003: Truth SQLite 结构化事实存储

## Status

Accepted

## Context

长篇小说需要跨章连续性。仅靠章节文本或 Markdown 摘要，无法稳定回答“前文发生了什么”“角色关系是否变了”“哪些设定不可逆”。系统还需要在章节 prompt 中检索相关事实，并在前端可视化。

## Decision

Truth 使用双写：每章 `truth/chapter-XXXX.json` 保存结构化备份，`books/truth.db` 的 `truth_entries` 表保存可检索事实。事实分为 plot_point、character_event、relationship、world_rule 等类别，检索使用关键词和重要度评分。

## Consequences

单书、本地、几十章规模下部署简单且检索够快；JSON 便于人工检查和备份。代价是关键词检索对复杂语义和 12 文明级世界观会退化，后续可能需要混合 RAG。

## Alternatives Considered

- 纯 Markdown 摘要：可读，但无法可靠检索和分级。
- JSON-only：简单，但缺少跨章搜索能力。
- 直接上向量数据库：语义强，但增加部署成本，不符合当前本地单用户 MVP。
