# Codex 指令：Phase 8A-1 — Python Sidecar 打包

> 发出日期：2026-06-11
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 7D 完成（448 后端 tests + 62 前端 tests, ruff clean）

---

## 任务概述

将 Python FastAPI 后端打包为 PyInstaller `--onedir` 可执行文件，集成到 Tauri 侧车（sidecar）架构中，使桌面应用无需用户手动安装 Python。

**当前状态**：
- `process_manager.rs` 的 `find_python()` 仅查找 `.venv/Scripts/python.exe`，找不到则报错
- `start()` 用 `Command::new(python).args(["-m", "storyforge3", "serve", ...])` 启动 FastAPI
- `Cargo.toml` 无 `tauri-plugin-shell` 依赖
- `capabilities/default.json` 无 shell 权限
- 无 PyInstaller 相关文件
- `pyproject.toml` 的依赖：`fastapi`, `uvicorn`, `pydantic>=2`, `pydantic-settings>=2`, `httpx>=0.27`, `ebooklib`, `sse-starlette`, `mcp`, `python-multipart`

**核心决策**：
1. **PyInstaller `--onedir`**（非 `--onefile`）— 避免 10-60 秒启动延迟和 kill 问题
2. **双模式启动**：有 sidecar 用 sidecar，没有则 fallback 到 venv Python（保持开发体验）
3. **仅 Windows** — `windows-x86_64-pc-windows-msvc` 目标三元组
4. **版本锁定**：Python backend 和 frontend 同版本发布，不走独立更新

---

## Part 1：Python 入口点

### 1.1 创建 `scripts/desktop_entry.py`

```python
"""PyInstaller entry point for StoryForge3 desktop backend.

Directly invokes uvicorn to avoid CLI parsing overhead and
module resolution issues in frozen mode.
"""
import sys
import uvicorn


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(
        "storyforge3.api.app:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
```

注意：直接调用 `uvicorn.run()` 而非 `-m storyforge3 serve`，避免 PyInstaller 冻结环境下 `sys.path` 和模块导入问题。

---

## Part 2：PyInstaller 配置

### 2.1 创建 `scripts/storyforge3-api.spec`

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for StoryForge3 API sidecar (--onedir)."""

block_cipher = None

hiddenimports = [
    # uvicorn submodules (dynamic imports)
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    # anyio backend
    "anyio._backends._asyncio",
    # FastAPI dependencies
    "httptools",
    # StoryForge3 web app (ensures import chain resolved)
    "storyforge3.api.app",
    "storyforge3.api.deps",
    "storyforge3.api.response",
    "storyforge3.api.errors",
    "storyforge3.api.routes",
    # pydantic-settings
    "pydantic_settings",
    # mcp sdk
    "mcp",
]

a = Analysis(
    ["scripts/desktop_entry.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "PIL", "scipy"],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="storyforge3-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="storyforge3-api",
)
```

---

## Part 3：构建脚本

### 3.1 创建 `scripts/build_sidecar.ps1`

```powershell
# Build StoryForge3 Python sidecar for Windows x86_64.
# Prerequisites: Python 3.11+, pip install pyinstaller
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts/build_sidecar.ps1

$ErrorActionPreference = "Stop"
$TargetTriple = "x86_64-pc-windows-msvc"
$BinaryName = "storyforge3-api-$TargetTriple"
$OutputDir = "src-tauri/binaries"

Write-Host "Building StoryForge3 sidecar..."

# Ensure output directory exists
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# Run PyInstaller
pyinstaller scripts/storyforge3-api.spec `
    --workpath build/sidecar-work `
    --distpath build/sidecar-dist `
    --clean `
    --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
    exit 1
}

# Copy the onedir output to src-tauri/binaries with target-triple suffix
$SourceDir = "build/sidecar-dist/storyforge3-api"
$DestDir = "$OutputDir/storyforge3-api"

if (Test-Path $DestDir) {
    Remove-Item -Recurse -Force $DestDir
}
Copy-Item -Recurse $SourceDir $DestDir

# Rename the main executable with target-triple suffix
$OldExe = "$DestDir/storyforge3-api.exe"
$NewExe = "$DestDir/$BinaryName.exe"
if (Test-Path $OldExe) {
    Move-Item -Force $OldExe $NewExe
}

Write-Host "Sidecar built successfully: $DestDir"
Write-Host "Main executable: $NewExe"

# Report size
$Size = (Get-ChildItem -Recurse $DestDir | Measure-Object -Property Length -Sum).Sum
$SizeMB = [math]::Round($Size / 1MB, 1)
Write-Host "Sidecar size: $SizeMB MB"
```

---

## Part 4：Tauri 侧车集成

### 4.1 更新 `src-tauri/Cargo.toml`

添加 `tauri-plugin-shell` 依赖：

```toml
tauri-plugin-shell = "2"
```

### 4.2 更新 `src-tauri/capabilities/default.json`

添加 shell spawn 权限：

```json
{
  "permissions": [
    "core:default",
    "dialog:default",
    "fs:write-files",
    "opener:default",
    "opener:allow-open-path",
    "process:default",
    "shell:allow-spawn",
    "store:default",
    "updater:default",
    "window-state:default"
  ]
}
```

### 4.3 更新 `src-tauri/tauri.conf.json`

在 `bundle` 中添加 `externalBin`：

```jsonc
{
  "bundle": {
    "active": true,
    "targets": "all",
    "createUpdaterArtifacts": true,
    "externalBin": ["binaries/storyforge3-api"],  // 新增
    // ...
  }
}
```

### 4.4 重构 `src-tauri/src/process_manager.rs`

**核心改动**：`start()` 方法改为双模式：
1. 优先查找 sidecar 二进制文件（`src-tauri/binaries/storyforge3-api-{target-triple}/storyforge3-api-{target-triple}.exe`）
2. 找不到 sidecar 则 fallback 到 venv Python（保持开发体验不变）

```rust
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use anyhow::Context;
use reqwest::Client;

/// Target triple for sidecar binary naming.
#[cfg(target_os = "windows")]
const TARGET_TRIPLE: &str = "x86_64-pc-windows-msvc";

pub struct ProcessManager {
    process: Mutex<Option<Child>>,
    port: u16,
    api_base: String,
}

impl ProcessManager {
    pub fn new(port: u16) -> Self {
        let api_base = format!("http://127.0.0.1:{port}");
        Self {
            process: Mutex::new(None),
            port,
            api_base,
        }
    }

    pub fn start(&self, project_dir: &Path) -> anyhow::Result<()> {
        // Strategy: sidecar first, venv fallback for development
        if let Some(sidecar_exe) = Self::find_sidecar(project_dir) {
            log::info!("Starting sidecar: {}", sidecar_exe.display());
            let port = self.port.to_string();
            let child = Command::new(&sidecar_exe)
                .args([&port])
                .env("PYTHONUNBUFFERED", "1")
                .current_dir(project_dir)
                .spawn()
                .with_context(|| format!("Failed to start sidecar: {}", sidecar_exe.display()))?;
            *self.process.lock().expect("process mutex poisoned") = Some(child);
            return Ok(());
        }

        // Fallback to venv Python (development mode)
        let python_path = Self::find_python(project_dir)?;
        log::info!(
            "Starting Python API server (dev mode): {} -m storyforge3 serve --port {}",
            python_path.display(),
            self.port
        );
        let port = self.port.to_string();
        let child = Command::new(&python_path)
            .args(["-m", "storyforge3", "serve", "--port", &port])
            .env("PYTHONUNBUFFERED", "1")
            .current_dir(project_dir)
            .spawn()
            .with_context(|| format!("Failed to start Python API server with {}", python_path.display()))?;
        *self.process.lock().expect("process mutex poisoned") = Some(child);
        Ok(())
    }

    pub async fn wait_for_health(&self, timeout_secs: u64) -> anyhow::Result<()> {
        // (unchanged — existing health check logic)
        // ...
    }

    pub fn stop(&self) -> anyhow::Result<()> {
        // (unchanged — child.kill() works correctly with --onedir)
        // ...
    }

    pub fn api_base(&self) -> &str {
        &self.api_base
    }

    /// Find sidecar binary: binaries/storyforge3-api-{triple}/storyforge3-api-{triple}.exe
    fn find_sidecar(project_dir: &Path) -> Option<PathBuf> {
        let exe_name = format!("storyforge3-api-{TARGET_TRIPLE}.exe");
        // Check relative to project_dir (could be repo root or src-tauri)
        for base in [
            project_dir.join("src-tauri").join("binaries"),
            project_dir.join("binaries"),
        ] {
            let sidecar = base.join(format!("storyforge3-api-{TARGET_TRIPLE}")).join(&exe_name);
            if sidecar.exists() {
                return Some(sidecar);
            }
        }
        None
    }

    pub(crate) fn find_python(project_dir: &Path) -> anyhow::Result<PathBuf> {
        #[cfg(target_os = "windows")]
        {
            let python = project_dir.join(".venv").join("Scripts").join("python.exe");
            if python.exists() {
                return Ok(python);
            }
        }

        #[cfg(not(target_os = "windows"))]
        {
            let python = project_dir.join(".venv").join("bin").join("python");
            if python.exists() {
                return Ok(python);
            }
        }

        anyhow::bail!(
            "Neither sidecar binary nor Python virtualenv found under {}. \
             Run scripts/build_sidecar.ps1 or set up .venv before launching desktop mode.",
            project_dir.display()
        )
    }
}
```

### 4.5 更新 `src-tauri/src/lib.rs`

在 plugin 注册中添加 `tauri_plugin_shell`：

```rust
let app = builder
    .plugin(tauri_plugin_process::init())
    .plugin(tauri_plugin_dialog::init())
    .plugin(tauri_plugin_fs::init())
    .plugin(tauri_plugin_opener::init())
    .plugin(tauri_plugin_shell::init())  // 新增
    .plugin(tauri_plugin_store::Builder::new().build())
    // ... 其余不变
```

---

## Part 5：借鉴来源

| 借鉴内容 | 来源文件 | 行数 | 借鉴方式 |
|---------|---------|------|---------|
| **Tauri v2 sidecar 模式** | [example-tauri-v2-python-server-sidecar](https://github.com/dieharders/example-tauri-v2-python-server-sidecar) | 全项目 | **架构复用**：PyInstaller + Tauri sidecar + FastAPI 的完整模式 |
| **PyInstaller hidden imports** | 同上项目的 `.spec` 配置 | ~20 行 | **直接复用**：uvicorn/anyio/httptools 隐藏导入列表 |
| **双模式启动（sidecar + fallback）** | CC-Switch `process_manager.rs` 中的 health check 模式 | ~30 行 | **模式复用**：优先外部二进制，fallback 到本地环境 |
| **process_manager.rs 现有结构** | SF3 `src-tauri/src/process_manager.rs` | 147 行 | **原地重构**：保持 find_python/wait_for_health/stop 不变，增加 find_sidecar |

**新写比例**：约 **40%**。process_manager 重构是增量修改（增加 find_sidecar + 双模式 start），PyInstaller 配置是新写的但模式成熟，构建脚本是全新的。

### 移植适配清单

| 源项目原始 | SF3 适配 |
|-----------|---------|
| example-tauri-v2 用 `--onefile` + stdin 信号关闭 | SF3 用 `--onedir` + 直接 child.kill()（更简单） |
| example-tauri-v2 用 `tauri_plugin_shell::ShellExt` sidecar API | SF3 用 `std::process::Command` 直接启动（避免 Tauri shell 权限复杂度，且保持统一接口） |
| example-tauri-v2 无 fallback（仅 sidecar） | SF3 增加 venv fallback 保持开发体验 |
| CC-Switch process_manager 直接 spawn python | SF3 增加前置 sidecar 检测 |

---

## 验收标准

### Python 入口 + PyInstaller

- [ ] `scripts/desktop_entry.py` 存在，直接调用 `uvicorn.run()`
- [ ] `scripts/storyforge3-api.spec` 包含必要的 hidden imports（uvicorn/anyio/httptools/pydantic_settings/mcp）
- [ ] `scripts/build_sidecar.ps1` 存在，生成 `src-tauri/binaries/storyforge3-api-x86_64-pc-windows-msvc/` 目录
- [ ] 构建脚本能成功执行（如果本机有 pyinstaller）或至少语法正确可审阅

### Tauri 集成

- [ ] `Cargo.toml` 添加 `tauri-plugin-shell = "2"`
- [ ] `lib.rs` 注册 `tauri_plugin_shell::init()`
- [ ] `capabilities/default.json` 添加 `shell:allow-spawn`
- [ ] `tauri.conf.json` bundle 添加 `externalBin: ["binaries/storyforge3-api"]`
- [ ] `process_manager.rs` 实现 `find_sidecar()` 方法
- [ ] `process_manager.rs` `start()` 实现 sidecar-first / venv-fallback 双模式
- [ ] `find_python()` 错误消息更新（提及 sidecar 和 venv 两个选项）
- [ ] 现有 `wait_for_health()` / `stop()` / `api_base()` / tests 不变

### Rust 质量

- [ ] `cargo check --manifest-path src-tauri/Cargo.toml` 通过（需要 cargo 环境）
- [ ] 现有 Rust tests 通过

### 后端质量

- [ ] 448 后端 tests 不退步
- [ ] `ruff check .` clean

---

## 估算工作量

| 部分 | 文件 | 预估行数 |
|------|------|---------|
| Python 入口 | `scripts/desktop_entry.py` | ~20 行新增 |
| PyInstaller spec | `scripts/storyforge3-api.spec` | ~60 行新增 |
| 构建脚本 | `scripts/build_sidecar.ps1` | ~50 行新增 |
| Cargo.toml | `src-tauri/Cargo.toml` | ~1 行改动 |
| lib.rs | `src-tauri/src/lib.rs` | ~1 行改动 |
| capabilities | `src-tauri/capabilities/default.json` | ~1 行改动 |
| tauri.conf.json | `src-tauri/tauri.conf.json` | ~1 行改动 |
| process_manager | `src-tauri/src/process_manager.rs` | ~40 行新增（find_sidecar + 双模式 start） |
| **合计** | **9 个文件** | **~175 行** |

---

## 不做的事（Out of Scope）

- ❌ 不在本机实际运行 PyInstaller（构建验证留给 CI 或手动触发）
- ❌ 不做 Nuitka 编译（PyInstaller 足够，Nuitka 是未来优化）
- ❌ 不做 macOS / Linux sidecar（仅 Windows）
- ❌ 不改 Python 后端代码（API 端点、Service 层不变）
- ❌ 不改前端代码
- ❌ 不实现 sidecar 独立更新（前后端版本锁定，全量安装包更新）
- ❌ 不处理 PyInstaller 杀毒误报（需要代码签名证书，超出范围）

---

## 事后勘误（2026-06-11）

PM 复盘确认：本指令编写前跳过了完整借鉴调研，Part 5 的借鉴来源需要修正。

1. **CC-Switch 归因不准确**：CC-Switch 是纯 Tauri/Rust 应用，没有 Python sidecar、PyInstaller 或外部二进制打包流程；不能作为 sidecar 架构借鉴来源。8A-1 的 sidecar-first / venv-fallback 逻辑应归类为 SF3 本阶段新写 + Tauri sidecar 模式参考。
2. **遗漏本地成熟参考**：仓库内 `storyforge/process/manuskript/manuskript.spec` 和 `storyforge/process/novelWriter/utils/build_binary.py` 是更直接的 PyInstaller 参考，应在实际打包验证阶段补读。
3. **待验证风险**：当前 spec 未显式配置 `datas`，后续真实打包必须检查 pydantic / FastAPI / MCP / 项目 package data 是否完整；PowerShell 脚本依赖 PATH 中的 `pyinstaller`，可考虑参考 novelWriter 改成 Python API 构建脚本。
4. **体积权衡**：`docs/research-sf3-gap-analysis.md` 中的纯 Tauri 便携分发基线约 8MB；引入 Python sidecar 会显著增大安装包，这是“作者开箱即用”相对“开发者便携版”的明确权衡。
