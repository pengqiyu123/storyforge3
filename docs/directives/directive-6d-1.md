# Codex 指令：Phase 6D-1 — Tauri 桌面端 Scaffold + Python 进程管理

> 发出日期：2026-06-09
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 6A-1 完成（334 后端 tests, 19 前端 tests, ruff clean）

---

## 任务概述

将 StoryForge3 Web 应用封装为 Tauri 2 桌面应用。**核心思路：Tauri 是进程管理器 + 桌面壳，不是业务逻辑层。** 所有业务逻辑保留在 Python FastAPI 中，Rust 只做三件事：

1. **启动/停止 Python API 服务器**（子进程管理）
2. **管理桌面窗口**（webview 加载 React 前端）
3. **系统托盘**（显示/隐藏/退出）

**前端零改动。** 所有 API 调用（`fetch('/api/...')`）照常通过 HTTP 到 `localhost:8000`。

---

## 核心约束：代码借鉴

**本指令的 Rust 代码 40% 来自 CC-Switch Tauri 层。**

| 借鉴来源 | 目标 | 借鉴方式 |
|----------|------|----------|
| `cc-switch-main/src-tauri/tauri.conf.json` (69行) | `src-tauri/tauri.conf.json` | 直接复制，改标识符/端口/前端路径 |
| `cc-switch-main/src-tauri/src/main.rs` (22行) | `src-tauri/src/main.rs` | 直接复制（Linux WebKit workaround） |
| `cc-switch-main/src-tauri/src/lib.rs` run() 前段 | `src-tauri/src/lib.rs` | 提取 plugin 注册 + setup 模式 |
| `cc-switch-main/src-tauri/build.rs` (28行) | `src-tauri/build.rs` | 直接复制 |
| `cc-switch-main/src-tauri/Cargo.toml` | `src-tauri/Cargo.toml` | 取子集（去掉不需要的依赖） |
| CC-Switch `main.tsx` init 模式 | 前端启动等待 | 参考 `get_init_error` 模式 |

**不从零编写的部分**：Tauri plugin 注册、窗口事件处理、托盘创建、build.rs。这些直接从 CC-Switch 移植。

**需要新写的部分**：Python 进程管理器（`process_manager.rs`），约 100 行。这是 SF3 特有的。

---

## 架构

```
┌──────────────────────────────────────────────────┐
│  StoryForge3 Desktop (Tauri 2.x)                │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  WebView                                    │  │
│  │  React 前端（零改动，现有代码不变）           │  │
│  │  fetch('/api/...') ──→ localhost:8000       │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ProcessManager (Rust, ~100 行)                  │
│  ├── spawn: .venv/Scripts/python -m storyforge3  │
│  │          serve --port 18731                   │
│  ├── health_check: GET /api/health (轮询)        │
│  └── shutdown: kill process on app exit          │
│                                                  │
│  System Tray: 显示 StoryForge3 / 隐藏 / 退出     │
│  Window State: 记住位置/大小                      │
│  Single Instance: 防止多开                        │
└──────────────────────────────────────────────────┘
```

### 为什么不用 Tauri IPC？

CC-Switch 把所有业务逻辑写在 Rust 里，前端通过 `invoke()` 调用。但 SF3 的业务逻辑已经在 Python 里（334 tests 覆盖），重写到 Rust 毫无意义。所以 SF3 的 Tauri 只是一个**智能启动器**——启动 Python 后端、加载前端、管理窗口生命周期。

---

## 文件结构

```
storyforge3/
├── src-tauri/                          # 新建 Tauri 项目
│   ├── Cargo.toml                      # 从 CC-Switch 取子集
│   ├── tauri.conf.json                 # 从 CC-Switch 复制并修改
│   ├── build.rs                        # 从 CC-Switch 复制
│   ├── icons/                          # 应用图标（占位）
│   │   ├── 32x32.png
│   │   ├── 128x128.png
│   │   ├── 128x128@2x.png
│   │   ├── icon.icns
│   │   └── icon.ico
│   └── src/
│       ├── main.rs                     # 从 CC-Switch 复制（22行）
│       ├── lib.rs                      # 借鉴 CC-Switch setup 模式
│       ├── process_manager.rs          # 新写：Python 进程管理
│       └── tray.rs                     # 借鉴 CC-Switch tray 模式
├── web/                                # 现有前端（几乎不改）
│   ├── src/
│   │   └── main.tsx                    # 微调：加 Tauri 环境检测 + 启动等待
│   └── package.json                    # 加 @tauri-apps/api 依赖 + scripts
└── src/                                # 现有后端（不改）
```

---

## 逐文件实现指令

### 1. `src-tauri/Cargo.toml`（新建）

从 CC-Switch `cc-switch-main/src-tauri/Cargo.toml` 取子集。**只保留 SF3 需要的**。

```toml
[package]
name = "storyforge3-desktop"
version = "0.1.0"
description = "StoryForge3 — Chinese web novel creation engine"
authors = ["StoryForge3 Team"]
license = "MIT"
edition = "2021"
rust-version = "1.85.0"

[lib]
name = "storyforge3_desktop_lib"
crate-type = ["staticlib", "cdylib", "rlib"]
doctest = false

[build-dependencies]
tauri-build = { version = "2.4.0", features = [] }

[dependencies]
tauri = { version = "2.8.2", features = ["tray-icon", "protocol-asset", "image-png"] }
tauri-plugin-log = "2"
tauri-plugin-opener = "2"
tauri-plugin-process = "2"
tauri-plugin-dialog = "2"
tauri-plugin-store = "2"
tauri-plugin-window-state = "2"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
log = "0.4"
tokio = { version = "1", features = ["macros", "rt-multi-thread", "time", "sync"] }
reqwest = { version = "0.12", features = ["rustls-tls", "json"] }
thiserror = "2.0"
anyhow = "1.0"
dirs = "5.0"

[target.'cfg(any(target_os = "macos", target_os = "windows", target_os = "linux"))'.dependencies]
tauri-plugin-single-instance = "2"

[profile.release]
codegen-units = 1
lto = "thin"
opt-level = "s"
panic = "unwind"
strip = "symbols"
```

**说明**：
- 去掉 CC-Switch 的 `rusqlite`、`axum`、`hyper`、`arboard`、`rquickjs`、`rusqlite` 等（SF3 不需要）
- 去掉 CC-Switch 的 `reqwest` 的 `stream`/`socks` features
- 去掉 `tauri-plugin-updater`（6D-2 再加）
- 去掉 `tauri-plugin-deep-link`（6D-2 再加）
- 保留 `tauri-plugin-single-instance`（防止多开）
- 保留 `reqwest`（用于 health check）

### 2. `src-tauri/tauri.conf.json`（新建）

从 CC-Switch `tauri.conf.json` (69行) 复制，修改以下字段：

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "StoryForge3",
  "version": "0.1.0",
  "identifier": "com.storyforge3.desktop",
  "build": {
    "frontendDist": "../web/dist",
    "devUrl": "http://localhost:5173",
    "beforeDevCommand": "pnpm --dir web run dev",
    "beforeBuildCommand": "pnpm --dir web run build"
  },
  "app": {
    "windows": [
      {
        "label": "main",
        "title": "StoryForge3",
        "titleBarStyle": "Overlay",
        "width": 1200,
        "height": 800,
        "minWidth": 900,
        "minHeight": 600,
        "visible": false,
        "resizable": true,
        "fullscreen": false,
        "center": true
      }
    ],
    "security": {
      "csp": "default-src 'self'; img-src 'self' data: https: http:; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' ipc: http://ipc.localhost https: http: http://localhost:18731 http://localhost:8000",
      "assetProtocol": {
        "enable": true,
        "scope": []
      }
    }
  },
  "bundle": {
    "active": true,
    "targets": "all",
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ],
    "windows": {
      "wix": null
    },
    "macOS": {
      "minimumSystemVersion": "12.0"
    }
  }
}
```

**与 CC-Switch 的差异**：
| 字段 | CC-Switch | SF3 | 原因 |
|------|-----------|-----|------|
| `productName` | CC Switch | StoryForge3 | 产品名 |
| `identifier` | com.ccswitch.desktop | com.storyforge3.desktop | 唯一标识 |
| `frontendDist` | ../dist | ../web/dist | SF3 前端在 web/ 下 |
| `devUrl` | localhost:3000 | localhost:5173 | SF3 Vite 端口 |
| `beforeDevCommand` | pnpm run dev:renderer | pnpm --dir web run dev | SF3 前端路径 |
| `beforeBuildCommand` | pnpm run build:renderer | pnpm --dir web run build | SF3 前端路径 |
| `title` | "" | StoryForge3 | 窗口标题 |
| `width/height` | 1000x650 | 1200x800 | 写作工具需要更大窗口 |
| CSP `connect-src` | 不含 localhost | 加 `localhost:18731` `localhost:8000` | 允许连接 Python 后端 |
| 去掉 `plugins` | deep-link + updater | 无 | 6D-2 再加 |

### 3. `src-tauri/src/main.rs`（新建）

**直接从 CC-Switch 复制**，改 crate 名：

```rust
// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    // 在 Linux 上设置 WebKit 环境变量以解决 DMA-BUF 渲染问题
    #[cfg(target_os = "linux")]
    {
        if std::env::var("WEBKIT_DISABLE_DMABUF_RENDERER").is_err() {
            std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
        }
        if std::env::var("WEBKIT_DISABLE_COMPOSITING_MODE").is_err() {
            std::env::set_var("WEBKIT_DISABLE_COMPOSITING_MODE", "1");
        }
    }

    storyforge3_desktop_lib::run();
}
```

### 4. `src-tauri/build.rs`（新建）

**直接从 CC-Switch 复制**（28行），需要创建 `common-controls.manifest` 文件：

```rust
fn main() {
    tauri_build::build();

    #[cfg(target_os = "windows")]
    {
        let manifest_path = std::path::PathBuf::from(
            std::env::var("CARGO_MANIFEST_DIR").expect("missing CARGO_MANIFEST_DIR"),
        )
        .join("common-controls.manifest");
        let manifest_arg = format!("/MANIFESTINPUT:{}", manifest_path.display());

        println!("cargo:rustc-link-arg=/MANIFEST:EMBED");
        println!("cargo:rustc-link-arg={}", manifest_arg);
        println!("cargo:rustc-link-arg-bins=/MANIFEST:NO");
        println!("cargo:rerun-if-changed={}", manifest_path.display());
    }
}
```

同时创建 `src-tauri/common-controls.manifest`（从 CC-Switch 复制，或在 `cc-switch-main/src-tauri/common-controls.manifest` 找到）。

### 5. `src-tauri/src/process_manager.rs`（新建，~120 行）

这是 SF3 唯一需要新写的核心模块。职责：管理 Python API 服务器的生命周期。

```rust
use std::path::PathBuf;
use std::process::Child;
use std::sync::Mutex;
use std::time::Duration;

use anyhow::Context;
use reqwest::Client;

/// Python API 进程管理器
///
/// 负责启动 `storyforge3 serve` 作为子进程，
/// 轮询 `/api/health` 直到就绪，
/// 并在应用退出时清理进程。
pub struct ProcessManager {
    process: Mutex<Option<Child>>,
    port: u16,
    api_base: String,
}

impl ProcessManager {
    /// 创建新的进程管理器
    ///
    /// `project_dir` 是 storyforge3 项目根目录（包含 .venv/）
    /// `port` 是 Python API 服务器监听端口
    pub fn new(project_dir: &str, port: u16) -> Self {
        let api_base = format!("http://127.0.0.1:{port}");
        Self {
            process: Mutex::new(None),
            port,
            api_base,
        }
    }

    /// 启动 Python API 服务器
    ///
    /// 使用项目目录下的 .venv 中的 Python 可执行文件
    pub fn start(&self, project_dir: &str) -> anyhow::Result<()> {
        let python_path = Self::find_python(project_dir)?;

        log::info!("Starting Python API server: {} serve --port {}", python_path.display(), self.port);

        let child = std::process::Command::new(&python_path)
            .args(["-m", "storyforge3", "serve", "--port", &self.port.to_string()])
            .env("PYTHONUNBUFFERED", "1")
            .current_dir(project_dir)
            .spawn()
            .with_context(|| format!("Failed to start Python server: {}", python_path.display()))?;

        *self.process.lock().unwrap() = Some(child);
        log::info!("Python API server started on port {}", self.port);
        Ok(())
    }

    /// 等待 API 服务器健康检查通过
    ///
    /// 轮询 `/api/health` 端点，最多等待 `timeout_secs` 秒
    pub async fn wait_for_health(&self, timeout_secs: u64) -> anyhow::Result<()> {
        let client = Client::builder()
            .timeout(Duration::from_secs(2))
            .build()
            .context("Failed to create HTTP client")?;

        let url = format!("{}/api/health", self.api_base);
        let start = std::time::Instant::now();
        let timeout = Duration::from_secs(timeout_secs);

        log::info!("Waiting for API health check at {url}...");

        loop {
            match client.get(&url).send().await {
                Ok(resp) if resp.status().is_success() => {
                    log::info!("API server is healthy ({}ms)", start.elapsed().as_millis());
                    return Ok(());
                }
                _ => {
                    if start.elapsed() > timeout {
                        anyhow::bail!(
                            "API server did not become healthy within {timeout_secs}s"
                        );
                    }
                    tokio::time::sleep(Duration::from_millis(500)).await;
                }
            }
        }
    }

    /// 停止 Python API 服务器
    pub fn stop(&self) -> anyhow::Result<()> {
        if let Ok(mut guard) = self.process.lock() {
            if let Some(mut child) = guard.take() {
                log::info!("Stopping Python API server (PID: {:?})...", child.id());
                // 先尝试优雅终止
                #[cfg(target_os = "windows")]
                {
                    // Windows: kill 是强制终止（等同于 TerminateProcess）
                    let _ = child.kill();
                }
                #[cfg(not(target_os = "windows"))]
                {
                    // Unix: 发送 SIGTERM
                    let _ = child.kill();
                }
                let _ = child.wait();
                log::info!("Python API server stopped");
            }
        }
        Ok(())
    }

    /// 查找项目目录下的 Python 可执行文件
    fn find_python(project_dir: &str) -> anyhow::Result<PathBuf> {
        let project = PathBuf::from(project_dir);

        // Windows: .venv/Scripts/python.exe
        #[cfg(target_os = "windows")]
        {
            let python = project.join(".venv").join("Scripts").join("python.exe");
            if python.exists() {
                return Ok(python);
            }
        }

        // Unix: .venv/bin/python
        #[cfg(not(target_os = "windows"))]
        {
            let python = project.join(".venv").join("bin").join("python");
            if python.exists() {
                return Ok(python);
            }
        }

        // 回退：系统 Python
        #[cfg(target_os = "windows")]
        {
            let python = PathBuf::from("python.exe");
            if which_exists(&python) {
                return Ok(python);
            }
        }

        #[cfg(not(target_os = "windows"))]
        {
            let python = PathBuf::from("python3");
            if which_exists(&python) {
                return Ok(python);
            }
        }

        anyhow::bail!(
            "Python not found. Searched: {}/.venv/ and system PATH",
            project_dir
        )
    }

    /// API 基础 URL（供前端查询用）
    pub fn api_base(&self) -> &str {
        &self.api_base
    }
}

fn which_exists(cmd: &PathBuf) -> bool {
    std::process::Command::new("which")
        .arg(cmd)
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

impl Drop for ProcessManager {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}
```

**注意**：当前的 `storyforge3 serve` CLI 命令只接受固定端口 8000。需要检查 `__main__.py` 是否支持 `--port` 参数。如果不支持，使用固定端口 8000 即可（6D-1 阶段简化处理）。

**如果 CLI 不支持 --port**，简化为：
```rust
.args(["-m", "storyforge3", "serve"])
```
端口固定 8000。

### 6. `src-tauri/src/tray.rs`（新建，~80 行）

借鉴 CC-Switch 的 `tray.rs` 模式，大幅简化：

```rust
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    AppHandle, Manager, Runtime,
};

pub const TRAY_ID: &str = "main-tray";

pub fn create_tray<R: Runtime>(app: &AppHandle<R>) -> anyhow::Result<()> {
    let show = MenuItem::with_id(app, "show", "显示 StoryForge3", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[&show, &quit])?;

    TrayIconBuilder::with_id(TRAY_ID)
        .icon(app.default_window_icon().cloned().unwrap())
        .menu(&menu)
        .tooltip("StoryForge3")
        .on_menu_event(move |app, event| match event.id().as_ref() {
            "show" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;

    Ok(())
}
```

### 7. `src-tauri/src/lib.rs`（新建，~120 行）

借鉴 CC-Switch `lib.rs` 的 `run()` 函数，提取以下模式：
- plugin 注册链
- setup 闭包
- 单实例检测
- 窗口事件处理

```rust
mod process_manager;
mod tray;

use process_manager::ProcessManager;
use std::sync::Arc;
use tauri::Manager;

fn window_state_flags() -> tauri_plugin_window_state::StateFlags {
    tauri_plugin_window_state::StateFlags::all()
}

#[tauri::command]
fn get_api_base(state: tauri::State<'_, Arc<ProcessManager>>) -> String {
    state.api_base().to_string()
}

#[tauri::command]
async fn get_init_status(state: tauri::State<'_, Arc<ProcessManager>>) -> Result<String, String> {
    // 如果能调到这里，说明进程已启动且健康检查已通过
    Ok("ready".to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let port: u16 = 8000;
    // 尝试检测项目目录（当前工作目录的父目录）
    let project_dir = std::env::current_dir()
        .unwrap_or_else(|_| ".".into())
        .to_string_lossy()
        .to_string();

    let pm = Arc::new(ProcessManager::new(&project_dir, port));

    let mut builder = tauri::Builder::default();

    // 单实例检测
    #[cfg(any(target_os = "macos", target_os = "windows", target_os = "linux"))]
    {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }));
    }

    builder
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(
            tauri_plugin_window_state::Builder::default()
                .with_state_flags(window_state_flags())
                .build(),
        )
        // 窗口关闭行为：隐藏到托盘
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
                #[cfg(target_os = "windows")]
                {
                    let _ = window.set_skip_taskbar(true);
                }
            }
        })
        .setup(move |app| {
            // 初始化日志
            {
                use tauri_plugin_log::{Target, TargetKind};

                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .targets([
                            Target::new(TargetKind::Stdout),
                            Target::new(TargetKind::Folder {
                                path: dirs::data_dir()
                                    .unwrap_or_else(|| ".".into())
                                    .join("storyforge3")
                                    .join("logs"),
                                file_name: Some("storyforge3".into()),
                            }),
                        ])
                        .build(),
                )?;
            }

            // 创建系统托盘
            tray::create_tray(app.handle())?;

            // 启动 Python 进程
            let pm_ref = Arc::clone(&pm);
            let app_handle = app.handle().clone();

            tauri::async_runtime::spawn(async move {
                if let Err(e) = pm_ref.start(&project_dir) {
                    log::error!("Failed to start Python server: {e}");
                    return;
                }

                // 等待健康检查（最多 30 秒）
                match pm_ref.wait_for_health(30).await {
                    Ok(()) => {
                        log::info!("Python API server is ready");
                        // 显示主窗口
                        if let Some(window) = app_handle.get_webview_window("main") {
                            let _ = window.show();
                        }
                    }
                    Err(e) => {
                        log::error!("Python API health check failed: {e}");
                        // TODO: 向前端发送错误事件
                    }
                }
            });

            // 注册进程管理器到 Tauri 状态
            app.manage(pm.clone());

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_api_base, get_init_status])
        .run(tauri::generate_context!())
        .expect("error while running StoryForge3 desktop app");
}
```

### 8. 前端微调：`web/src/main.tsx`

添加 Tauri 环境检测。**只在 Tauri 环境下**才做启动等待。

**当前代码**（28行）不删除，在 `ReactDOM.createRoot` 之前加一段：

```typescript
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { App } from "@/App";
import { Toaster } from "@/components/ui/sonner";
import "@/globals.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false
    }
  }
});

// Tauri 环境检测：如果是桌面端，等待 Python API 就绪
async function waitForApi() {
  // 只在 Tauri 环境下等待
  if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
    const maxRetries = 60; // 最多等待 30 秒
    for (let i = 0; i < maxRetries; i++) {
      try {
        const resp = await fetch("http://localhost:8000/api/health");
        if (resp.ok) return;
      } catch {
        // 还没启动
      }
      await new Promise((r) => setTimeout(r, 500));
    }
  }
}

waitForApi().then(() => {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
          <Toaster />
        </BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>
  );
});
```

**注意**：这段代码在 Web 模式下（非 Tauri）行为不变——`__TAURI_INTERNALS__` 不存在时直接跳过等待。

### 9. `web/package.json` 新增依赖和 scripts

在 `web/package.json` 中添加：

```json
{
  "dependencies": {
    "@tauri-apps/api": "^2"
  },
  "scripts": {
    "tauri": "tauri",
    "dev:desktop": "tauri dev",
    "build:desktop": "tauri build"
  }
}
```

安装命令：
```powershell
cd web
pnpm add @tauri-apps/api
```

同时需要在项目根目录（`storyforge3/`）安装 Tauri CLI：
```powershell
cd storyforge3
pnpm add -D @tauri-apps/cli
```

### 10. `src-tauri/icons/`（占位图标）

创建 5 个占位图标文件（可以先从 CC-Switch 复制图标作为临时方案，或生成纯色占位）：
- `32x32.png`
- `128x128.png`
- `128x128@2x.png`
- `icon.icns`（macOS）
- `icon.ico`（Windows）

### 11. 后端：CLI `--port` 参数（如果不存在）

检查 `src/storyforge3/__main__.py` 的 `serve` 命令是否支持 `--port` 参数。如果不支持，添加：

```python
if args.command == "serve":
    port = getattr(args, 'port', 8000)
    import uvicorn
    uvicorn.run("storyforge3.api.app:app", host="127.0.0.1", port=port, reload=False)
```

**注意**：
- 桌面端模式不需要 `reload=True`
- `host` 改为 `127.0.0.1`（只监听本地，安全）
- 如果改 CLI 有风险，6D-1 先用固定端口 8000，后续再加 `--port`

---

## Rust 代码规范

**严格遵循项目 Rust 规则**（`~/.claude/rules/rust/`）：

1. **`cargo fmt`** — 提交前格式化
2. **`cargo clippy -- -D warnings`** — lint 无警告
3. **`&str` 优于 `String`** — 函数参数用借用
4. **`Result<T, E>` + `?`** — 不用 `unwrap()`（测试除外）
5. **`thiserror`** — 库错误用 typed error
6. **`anyhow`** — 应用错误用 context chain
7. **按领域组织模块** — process_manager、tray 各自独立
8. **可见性最小** — 默认 private，需要暴露的用 `pub(crate)`

---

## 测试

### Rust 测试

在 `src-tauri/src/process_manager.rs` 中添加 `#[cfg(test)]` 模块：

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_creates_manager_with_correct_port() {
        let pm = ProcessManager::new("/tmp", 8000);
        assert_eq!(pm.api_base(), "http://127.0.0.1:8000");
    }

    #[test]
    fn find_python_returns_error_for_missing_venv() {
        let result = ProcessManager::find_python("/nonexistent/path");
        assert!(result.is_err());
    }
}
```

运行：
```powershell
cd storyforge3/src-tauri
cargo test
cargo clippy -- -D warnings
cargo fmt --check
```

### 前端测试

现有的 19 个前端测试不应退步。新增一个 Tauri 环境检测测试（可选）。

### 后端测试

现有的 334 个后端测试不应退步。如果修改了 `__main__.py` 添加 `--port`，添加对应测试。

---

## 验收标准

```powershell
# 1. Rust 编译 + lint
cd storyforge3/src-tauri
cargo build                    # 编译成功
cargo clippy -- -D warnings    # 无警告
cargo fmt --check              # 格式正确
cargo test                     # Rust 测试通过

# 2. 前端不退步
cd storyforge3/web
pnpm build                     # tsc + vite build 零错误
pnpm test                      # 19 前端 tests 通过

# 3. 后端不退步
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ -q   # 334 tests 通过
ruff check .                                       # clean

# 4. Tauri 开发模式（手动验证，可选）
cd storyforge3
pnpm tauri dev                  # 桌面窗口弹出，加载前端
                                # Python 进程自动启动
                                # 关闭窗口后进程清理
```

功能验收：
1. `pnpm tauri dev` 启动桌面应用，窗口弹出
2. 窗口内显示 StoryForge3 前端（Dashboard/Books 等页面）
3. Python API 服务器作为子进程自动启动
4. `/api/health` 健康检查通过后才显示主窗口
5. 系统托盘图标可见，点击可显示/隐藏窗口
6. 关闭窗口最小化到托盘（不退出）
7. 托盘菜单"退出"关闭应用并清理 Python 进程
8. 前端 API 调用正常（Book CRUD、Pipeline 等）
9. SSE 事件流正常
10. 单实例检测（已运行时再次启动只聚焦窗口）
11. 全部 334 后端 + 19 前端 + Rust 测试通过
12. ruff check clean + cargo clippy clean

---

## 不在 6D-1 范围内

| 功能 | 归属 | 原因 |
|------|------|------|
| 自动更新 | 6D-2 | 需要 GitHub Release pipeline |
| 深链接 | 6D-2 | 非核心功能 |
| Python 打包 | 6D-2 或更后 | 复杂度极高，先要求用户安装 Python |
| 原生文件对话框 | 6D-2 | 先用 Web File API |
| 应用签名/公证 | 6D-2 | 需要 Apple Developer / Windows 证书 |

---

## 参考文件

### 必须读取（借鉴来源）

1. **`d:\python\Novel\cc-switch-main\src-tauri\tauri.conf.json`** — 配置模板（69行）
2. **`d:\python\Novel\cc-switch-main\src-tauri\src\main.rs`** — 入口模板（22行）
3. **`d:\python\Novel\cc-switch-main\src-tauri\src\lib.rs`** — setup/plugin 注册模式（前 280 行）
4. **`d:\python\Novel\cc-switch-main\src-tauri\Cargo.toml`** — 依赖版本号（108行）
5. **`d:\python\Novel\cc-switch-main\src-tauri\build.rs`** — 构建脚本（28行）
6. **`d:\python\Novel\cc-switch-main\src-tauri\common-controls.manifest`** — Windows manifest

### 需要检查

7. **`d:\python\Novel\storyforge3\src\storyforge3\__main__.py`** — CLI serve 命令是否有 --port

### 需要修改

8. `storyforge3/web/src/main.tsx` — 加 Tauri 环境检测
9. `storyforge3/web/package.json` — 加 @tauri-apps/api 依赖 + scripts

### 新建（全部在 src-tauri/）

10. `src-tauri/Cargo.toml`
11. `src-tauri/tauri.conf.json`
12. `src-tauri/build.rs`
13. `src-tauri/common-controls.manifest`
14. `src-tauri/src/main.rs`
15. `src-tauri/src/lib.rs`
16. `src-tauri/src/process_manager.rs`
17. `src-tauri/src/tray.rs`
18. `src-tauri/icons/*`（5 个图标文件）

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 6D-1（Tauri 桌面端 Scaffold）：
- Tauri 项目创建：[完成状态 + Cargo.toml 依赖列表]
- process_manager.rs：[完成状态 + 行数]
- tray.rs：[完成状态 + 行数]
- lib.rs：[完成状态 + plugin 列表]
- 前端 main.tsx 修改：[完成状态]
- 后端 __main__.py --port：[是否修改 + 状态]
- Rust 测试：[数量] passed
- cargo clippy：[状态]
- cargo fmt：[状态]
- 前端测试：[数量] passed
- 后端测试：[数量] passed
- pnpm tauri dev 手动测试：[状态]
- 改动文件列表：[...]
```
