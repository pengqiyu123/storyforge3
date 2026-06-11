# ADR-002: React 19 + Vite 前端

## Status

Accepted

## Context

StoryForge3 需要一个本地 Web 工作台，让作者能创建书籍、操作章节管线、编辑正文、查看审计、truth、快照和导出预览。参考项目中，React 生态的 ANWA 与 InkOS 质量较高，Vue 参考项目存在 god component、弱类型和零测试问题。

## Decision

采用 React 19 + Vite + TypeScript + Tailwind + shadcn/ui。服务端状态使用 React Query，编辑器采用从 CC-Switch 移植的 CodeMirror 6。前端通过 FastAPI HTTP/SSE 调用后端，不直接访问 Python service。

## Consequences

开发体验快，组件和测试生态成熟，适合后续封装到 Tauri。代价是需要 Node/pnpm 工具链，并要维护 TypeScript 类型和后端 Pydantic 响应的一致性。

## Alternatives Considered

- Vue 3 + Element Plus：组件成熟，但本项目可借鉴代码质量低，TypeScript 和测试样板不足。
- Next.js：会引入 Node 服务端，与 Python FastAPI 主体冲突。
- 纯 CLI：工程简单，但无法满足作者日常编辑、审计定位和质量运营需求。
