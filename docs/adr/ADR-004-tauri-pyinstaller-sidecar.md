# ADR-004: Tauri 2 + PyInstaller Sidecar 桌面分发

## Status

Accepted

## Context

StoryForge3 的业务核心在 Python FastAPI。桌面用户不应手动安装 Python、启动后端再打开浏览器；但将全部业务重写成 Rust 成本过高。还需要控制安装包体积，避免 Electron 级别的重量。

## Decision

采用 Tauri 2 作为桌面壳，Rust 只负责窗口、托盘、进程管理和 health check。Python 后端通过 PyInstaller `--onedir` 打包为 sidecar；开发环境保留 `.venv` fallback。

## Consequences

用户可获得近似开箱即用的桌面体验，前端仍通过 HTTP/SSE 与 FastAPI 通信。代价是 sidecar 会显著增大包体积，并需要额外验证 hidden imports、package data、杀毒误报和 updater artifact。

## Alternatives Considered

- Electron：成熟但体积大，和本地轻量工具定位冲突。
- 纯 Tauri/Rust 后端：体积最小，但要重写 Python LLM、审计和 truth 生态。
- Nuitka：可能更利于发布和防逆向，但当前未验证，先保留为后续打包优化选项。
