# ADR-005: CC-Switch 只读集成 + Provider 路由

## Status

Accepted

## Context

用户已经在 CC-Switch 中维护中转站和模型配置。StoryForge3 如果再实现一套 provider 管理，会重复造轮子，也容易引入密钥泄漏和配置漂移。另一方面，SF3 需要自己记录 active provider、任务模型路由和调用日志。

## Decision

StoryForge3 只读 CC-Switch SQLite provider 数据库，通过 `CCSwitchDBReader` 导入 provider 到本地 `.storyforge3/providers.json`。运行时由 `LLMService` 直连 provider API，并支持 OpenAI Chat、OpenAI Responses、Anthropic Messages 和 Gemini Native 多协议路由。

## Consequences

Provider 管理委托给 CC-Switch，SF3 聚焦创作流程；密钥只留在本地 ignored 配置中。代价是首次使用依赖用户已有 CC-Switch 配置，且 provider 行为不稳定时需要更强 health check 和错误提示。

## Alternatives Considered

- SF3 自建 Provider GUI：可控但重复成本高，并增加安全面。
- 硬编码单 provider：实现快，但无法适配用户已有中转站。
- 通过 CC-Switch 请求代理转发：多一层运行依赖和网络跳转，本项目只需要读取配置后直连。
