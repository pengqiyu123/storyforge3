# Codex 指令：Phase 6D-2 — Tauri 桌面端 Polish（自动更新 + 启动错误 UI + 原生导出）

> 发出日期：2026-06-09
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 6D-1 完成（335 后端 tests, 23 前端 tests, 4 Rust tests, ruff/cargo clean）

---

## 任务概述

Phase 6D-1 交付了 Tauri 桌面壳：Python 进程管理、系统托盘、窗口生命周期、单实例检测。本阶段在 6D-1 基础上补齐三个生产级桌面体验：

1. **自动更新**：用户无需手动下载新版，应用内检查 → 下载 → 安装 → 重启
2. **启动错误 UI**：Python 启动失败或健康检查超时时，展示可操作错误页而非空白窗口
3. **原生导出对话框**：导出书籍时弹出系统级保存对话框，用户选择目录

**核心原则**：自动更新的前端代码 ~90% 从 CC-Switch 移植，启动错误和原生对话框为新写但量小（各 ~50 行）。

---

## 功能 1：自动更新系统

### 架构

```
Tauri Plugin Updater（Rust 侧）
  ├── tauri-plugin-updater 注册（1 行）
  ├── tauri.conf.json 配置 pubkey + endpoint
  └── GitHub Release 发布 latest.json + 签名安装包

前端（从 CC-Switch 移植）
  ├── web/src/lib/updater.ts           — 检查/下载/安装 API 封装
  ├── web/src/contexts/UpdateContext.tsx — React Context + 自动检查
  └── web/src/components/UpdateBanner.tsx — 更新提示横幅
```

### Rust 侧改动

#### 1.1 `src-tauri/Cargo.toml` — 新增依赖

在 `[dependencies]` 中添加：

```toml
tauri-plugin-updater = "2"
```

#### 1.2 `src-tauri/src/lib.rs` — 注册插件

在 setup 闭包内（`tray::create_tray` 之后）添加：

```rust
app.handle().plugin(tauri_plugin_updater::Builder::new().build())?;
```

#### 1.3 `src-tauri/tauri.conf.json` — 添加 updater 配置

在 JSON 根级添加 `plugins` 字段：

```json
{
  "plugins": {
    "updater": {
      "endpoints": [
        "https://github.com/farion1231/storyforge3/releases/latest/download/latest.json"
      ]
    }
  }
}
```

**注意**：
- `pubkey` 字段暂不填（签名在发布阶段配置，6D-2 先用无签名模式验证流程）
- `createUpdaterArtifacts` 暂不加到 bundle（等发布流程就绪后再开）
- GitHub 仓库地址 `farion1231/storyforge3` 是占位，需确认实际仓库

#### 1.4 `src-tauri/capabilities/default.json` — 添加权限

如果该文件存在，添加 updater 权限。如果不存在则创建：

```json
{
  "$schema": "https://schema.tauri.app/config/2/capability",
  "identifier": "default",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "updater:default",
    "dialog:default",
    "store:default",
    "window-state:default",
    "process:default",
    "opener:default"
  ]
}
```

### 前端改动

#### 1.5 `web/src/lib/updater.ts`（新建，从 CC-Switch 移植）

**借鉴来源**：`cc-switch-main/src/lib/updater.ts`（124 行）

从 CC-Switch 移植，修改点：
- 去掉 `UpdateChannel` 类型（SF3 没有 beta/stable 通道）
- 去掉 `mapUpdateHandle` 中的 `any` 类型转换，用 `@tauri-apps/plugin-updater` 的原生类型
- 保留 `UpdaterPhase` 状态机：idle → checking → available → downloading → installing → restarting / upToDate / error
- 保留 `checkForUpdate()` 和 `relaunchApp()` 两个核心函数

简化后约 80 行（CC-Switch 124 行中大量是类型兼容映射，SF3 不需要）。

```typescript
// 核心接口（简化版）
export type UpdaterPhase =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "installing"
  | "restarting"
  | "upToDate"
  | "error";

export interface UpdateInfo {
  currentVersion: string;
  availableVersion: string;
  notes?: string;
  pubDate?: string;
}

export async function checkForUpdate(): Promise<{
  status: "up-to-date";
} | {
  status: "available";
  info: UpdateInfo;
  downloadAndInstall: (onProgress?: (progress: { downloaded: number; total: number }) => void) => Promise<void>;
}> {
  // 动态 import @tauri-apps/plugin-updater
  // 调用 check()
  // 映射返回值
}

export async function getCurrentVersion(): Promise<string> {
  // 从 @tauri-apps/api/app 获取版本号
}

export async function relaunchApp(): Promise<void> {
  // 从 @tauri-apps/plugin-process 调用 relaunch()
}
```

#### 1.6 `web/src/contexts/UpdateContext.tsx`（新建，从 CC-Switch 移植）

**借鉴来源**：`cc-switch-main/src/contexts/UpdateContext.tsx`（156 行）

从 CC-Switch 移植，修改点：
- 去掉 legacy key 迁移逻辑（SF3 没有旧版本键）
- 去掉 `UpdateChannel` 参数
- 保留核心：自动启动检查、dismiss 版本、checkUpdate 方法

简化后约 80 行。

```typescript
interface UpdateContextValue {
  hasUpdate: boolean;
  updateInfo: UpdateInfo | null;
  isChecking: boolean;
  isUpdating: boolean;
  downloadProgress: { downloaded: number; total: number } | null;
  error: string | null;
  isDismissed: boolean;
  dismissUpdate: () => void;
  checkUpdate: () => Promise<boolean>;
  startUpdate: () => Promise<void>;
}
```

#### 1.7 `web/src/components/UpdateBanner.tsx`（新建）

当有可用更新且未被关闭时，在应用顶部显示金色横幅：

```
┌─────────────────────────────────────────────────────────┐
│ 🔄 新版本 v0.2.0 可用 [查看详情] [立即更新] [忽略]       │
└─────────────────────────────────────────────────────────┘
```

- 使用 shadcn `Banner` 或 `Alert` 组件
- 点击「立即更新」：显示下载进度条 → 安装 → 重启
- 点击「忽略」：关闭横幅，记住到 localStorage（按版本号）
- 只在 Tauri 环境下显示（非 Tauri 环境不渲染）

约 60 行。

#### 1.8 `web/src/App.tsx` — 包裹 UpdateProvider

在 App 根组件中添加 `UpdateProvider` 包裹。**只在 Tauri 环境下激活**：

```typescript
import { isTauriEnvironment } from "@/tauriBootstrap";

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {isTauriEnvironment() && <UpdateProvider><UpdateBanner /></UpdateProvider>}
        {/* 现有路由 */}
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

#### 1.9 `web/package.json` — 新增依赖

```json
{
  "dependencies": {
    "@tauri-apps/plugin-updater": "^2"
  }
}
```

安装命令：
```powershell
cd web && pnpm add @tauri-apps/plugin-updater
```

---

## 功能 2：启动错误 UI

### 问题

6D-1 的当前行为：Python 启动失败或 30 秒健康检查超时 → 日志记录错误 → 主窗口不显示 → 用户看到什么都没有。

### 解决方案

Rust 侧通过 Tauri event 将启动状态推送到前端，前端根据状态显示不同的启动画面。

### Rust 侧改动

#### 2.1 `src-tauri/src/lib.rs` — 发送启动事件

在 setup 闭包的 `tauri::async_runtime::spawn` 中，修改 Python 启动和健康检查的 error 分支：

```rust
// 成功时
if let Some(window) = app_handle.get_webview_window("main") {
    let _ = window.show();
}

// 失败时（替换当前的 log::error）
Err(error) => {
    log::error!("Python API startup failed: {error:#}");
    let _ = app_handle.emit("python-startup-error", error.to_string());
    // 仍然显示窗口，让前端展示错误 UI
    if let Some(window) = app_handle.get_webview_window("main") {
        let _ = window.show();
    }
}
```

**关键变化**：即使 Python 启动失败也要显示窗口（当前是不显示），让前端能展示错误信息。

### 前端改动

#### 2.2 `web/src/components/StartupErrorScreen.tsx`（新建）

当收到 `python-startup-error` 事件时，替换整个应用内容为错误屏幕：

```
┌─────────────────────────────────────────┐
│                                         │
│         ⚠️ StoryForge3 启动失败         │
│                                         │
│    Python API 服务器未能启动。           │
│    错误信息：{具体错误}                   │
│                                         │
│    请检查：                              │
│    · Python 虚拟环境是否已安装           │
│    · 端口 8000 是否被占用                │
│    · 依赖包是否完整                      │
│                                         │
│         [重试]    [查看日志]             │
│                                         │
└─────────────────────────────────────────┘
```

- `重试` 按钮：调用 `location.reload()` 刷新页面（触发重新等待 API）
- `查看日志` 按钮：打开日志目录（调用 `@tauri-apps/plugin-opener` 打开文件夹）
- 只在 Tauri 环境下注册事件监听

约 50 行。

#### 2.3 `web/src/App.tsx` — 集成启动错误监听

在 App 中监听 `python-startup-error` 事件，设置 `startupError` 状态：

```typescript
const [startupError, setStartupError] = useState<string | null>(null);

useEffect(() => {
  if (!isTauriEnvironment()) return;
  // 监听 Tauri event
  const unlisten = listen<string>("python-startup-error", (event) => {
    setStartupError(event.payload);
  });
  return () => { unlisten.then(fn => fn()); };
}, []);

if (startupError) {
  return <StartupErrorScreen error={startupError} />;
}
```

---

## 功能 3：原生导出对话框

### 当前行为

导出书籍（TXT/MD/EPUB/Qidian）时，前端调用 `GET /api/books/{id}/export?format=txt`，后端返回文件内容。前端通过浏览器下载保存到默认下载目录。

### 目标行为

在 Tauri 桌面模式下，弹出系统级保存对话框，让用户选择保存位置和文件名。

### 改动

#### 3.1 `web/src/api/client.ts` — 添加桌面模式导出辅助函数

```typescript
import { save } from "@tauri-apps/plugin-dialog";
import { writeFile } from "@tauri-apps/plugin-opener";
import { isTauriEnvironment } from "@/tauriBootstrap";

export async function exportBookDesktop(
  bookId: string,
  format: string,
  bookTitle: string,
): Promise<string | null> {
  if (!isTauriEnvironment()) return null;

  const extensions: Record<string, string[]> = {
    txt: ["txt"],
    md: ["md"],
    epub: ["epub"],
    qidian: ["txt"],
  };

  const filePath = await save({
    defaultPath: `${bookTitle}.${format}`,
    filters: [{
      name: format.toUpperCase(),
      extensions: extensions[format] || ["txt"],
    }],
  });

  if (!filePath) return null; // 用户取消

  // 下载文件内容
  const response = await fetch(resolveApiUrl(`/api/books/${bookId}/export?format=${format}`));
  const blob = await response.blob();
  const arrayBuffer = await blob.arrayBuffer();
  const uint8Array = new Uint8Array(arrayBuffer);

  await writeFile(filePath, uint8Array);
  return filePath;
}
```

#### 3.2 修改现有的导出调用点

找到前端中调用导出 API 的组件，添加 Tauri 分支：

```typescript
async function handleExport(format: string) {
  if (isTauriEnvironment()) {
    const savedPath = await exportBookDesktop(bookId, format, bookTitle);
    if (savedPath) {
      toast.success(`已导出到 ${savedPath}`);
      return;
    }
    // 用户取消对话框，不继续
    return;
  }
  // Web 模式：现有逻辑不变
  // ... 原有的 window.open / download 逻辑
}
```

**需要检查的文件**：搜索前端代码中调用 `/export` 或 `exportBook` 的位置，确认改动点。

#### 3.3 `web/package.json` — 确认依赖

`@tauri-apps/plugin-dialog` 已在 6D-1 安装。确认 `@tauri-apps/plugin-opener` 也已安装（6D-1 的 `Cargo.toml` 已有 `tauri-plugin-opener`，前端需要对应的 `@tauri-apps/plugin-opener` 包）。

如果前端 package.json 没有 `@tauri-apps/plugin-opener`，添加：

```powershell
cd web && pnpm add @tauri-apps/plugin-opener
```

---

## 文件改动清单

### Rust 侧（~5 行新增）

| 文件 | 操作 | 说明 |
|------|------|------|
| `src-tauri/Cargo.toml` | 修改 | 加 `tauri-plugin-updater = "2"` |
| `src-tauri/src/lib.rs` | 修改 | 加 updater 插件注册（1 行）+ 启动失败时 emit 事件 + 显示窗口 |
| `src-tauri/tauri.conf.json` | 修改 | 加 `plugins.updater` 配置 |
| `src-tauri/capabilities/default.json` | 新建 | 权限声明（如果不存在） |

### 前端（~320 行新增）

| 文件 | 操作 | 说明 |
|------|------|------|
| `web/src/lib/updater.ts` | 新建 ~80 行 | 从 CC-Switch `updater.ts` 移植 |
| `web/src/contexts/UpdateContext.tsx` | 新建 ~80 行 | 从 CC-Switch `UpdateContext.tsx` 移植 |
| `web/src/components/UpdateBanner.tsx` | 新建 ~60 行 | 更新提示横幅 |
| `web/src/components/StartupErrorScreen.tsx` | 新建 ~50 行 | 启动错误屏幕 |
| `web/src/api/client.ts` | 修改 | 加 `exportBookDesktop()` 函数 |
| `web/src/App.tsx` | 修改 | 包裹 UpdateProvider + 启动错误监听 |
| 导出调用点组件 | 修改 | 添加 Tauri 分支 |
| `web/package.json` | 修改 | 加 `@tauri-apps/plugin-updater`，确认 `plugin-opener` |

### 后端

无改动。

---

## 借鉴来源

| 功能 | CC-Switch 文件 | 行数 | 借鉴方式 |
|------|----------------|------|----------|
| 自动更新 Rust | `cc-switch-main/src-tauri/src/lib.rs:297` | 1 行 | 复制注册模式 |
| 自动更新配置 | `cc-switch-main/src-tauri/tauri.conf.json:62-68` | 7 行 | 复制结构，改 endpoint |
| 自动更新前端 | `cc-switch-main/src/lib/updater.ts` | 124 行 | 移植，简化类型映射 |
| 更新 Context | `cc-switch-main/src/contexts/UpdateContext.tsx` | 156 行 | 移植，去掉 legacy 迁移 |
| 关于页 UI 参考 | `cc-switch-main/src/components/settings/AboutSection.tsx` | — | 参考 UI 布局，不直接移植 |

**不借鉴**：
- CC-Switch deep link 系统（`deeplink/` 目录，~800 行）— CC-Switch 专属，SF3 无用例
- CC-Switch 应用签名（需要 Apple Developer / Windows 证书）— 发布阶段再处理

---

## 测试

### Rust

```powershell
cd storyforge3/src-tauri
cargo build
cargo clippy -- -D warnings
cargo fmt --check
cargo test
```

### 前端

```powershell
cd storyforge3/web
pnpm build              # tsc + vite build 零错误
pnpm test               # 全部测试通过
```

新增测试：
- `updater.test.ts`：mock `@tauri-apps/plugin-updater`，测试 `checkForUpdate()` 返回 up-to-date / available
- `UpdateContext.test.tsx`：测试 checkUpdate 调用、dismiss 逻辑
- `StartupErrorScreen.test.tsx`：测试错误显示和重试按钮
- `client.test.ts`：测试 `exportBookDesktop()` 在非 Tauri 环境返回 null

### 后端

```powershell
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ -q   # 335 tests 不退步
ruff check .
```

---

## 验收标准

### 自动更新

- [ ] `cargo build` 通过，`tauri-plugin-updater` 正确注册
- [ ] `tauri.conf.json` 包含 `plugins.updater.endpoints` 配置
- [ ] 前端 `updater.ts` 正确封装 check/download/install API
- [ ] `UpdateContext` 在应用启动 2 秒后自动检查更新
- [ ] `UpdateBanner` 在有更新时显示横幅，点击可下载安装
- [ ] 忽略的版本号存入 localStorage，不重复提示
- [ ] 非 Tauri 环境下自动更新功能完全不渲染、不报错

### 启动错误 UI

- [ ] Python 启动失败时，窗口仍然显示（不是空白不出现）
- [ ] 前端收到 `python-startup-error` 事件后展示 `StartupErrorScreen`
- [ ] 错误屏幕显示具体错误信息
- [ ] 「重试」按钮刷新页面重新等待 API
- [ ] 「查看日志」打开日志目录
- [ ] 非 Tauri 环境下此功能不激活

### 原生导出对话框

- [ ] Tauri 桌面模式下点击导出，弹出系统保存对话框
- [ ] 对话框默认文件名为 `{书名}.{格式}`
- [ ] 选择路径后文件正确保存
- [ ] 取消对话框不触发错误
- [ ] 非 Tauri 环境下保持原有 Web 下载行为不变

### 质量门

- [ ] Rust：cargo test 全绿，clippy 零 warning，fmt 格式正确
- [ ] 前端：pnpm test 全绿（23+ 现有 + 4 新增），pnpm build 零错误
- [ ] 后端：pytest 335 tests 不退步，ruff clean

---

## 不在 6D-2 范围内

| 功能 | 归属 | 原因 |
|------|------|------|
| 深链接 | 不做 | CC-Switch 专属（导入 provider/MCP），SF3 无用例 |
| Python 打包 | 远期 | 需要嵌入 Python 运行时，复杂度极高 |
| 应用签名/公证 | 发布阶段 | 需要 Apple Developer / Windows 证书 |
| CI Release pipeline | 运维 | 需要单独规划 GitHub Actions + 签名流程 |
| 多窗口 | 不做 | 写作工具不需要多窗口 |

---

## 参考文件

### 必须读取（借鉴来源）

1. **`d:\python\Novel\cc-switch-main\src\lib\updater.ts`** — 更新 API 封装（124 行）
2. **`d:\python\Novel\cc-switch-main\src\contexts\UpdateContext.tsx`** — 更新 Context（156 行）
3. **`d:\python\Novel\cc-switch-main\src-tauri\tauri.conf.json`** — updater 配置（62-68 行）
4. **`d:\python\Novel\cc-switch-main\src-tauri\src\lib.rs`** — updater 注册模式（297 行）

### 当前项目文件（需要修改）

5. **`storyforge3/src-tauri/Cargo.toml`** — 添加 updater 依赖
6. **`storyforge3/src-tauri/src/lib.rs`** — 注册 updater + emit 启动事件
7. **`storyforge3/src-tauri/tauri.conf.json`** — 添加 plugins.updater
8. **`storyforge3/web/src/App.tsx`** — 包裹 UpdateProvider + 启动错误监听
9. **`storyforge3/web/src/api/client.ts`** — 添加 exportBookDesktop()
10. **`storyforge3/web/package.json`** — 添加 plugin-updater

### 需要搜索确认

11. 前端导出调用点（搜索 `export` 或 `/api/books/` + `export` 相关组件）

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 6D-2（Tauri 桌面端 Polish）：

功能 1 — 自动更新：
- Rust updater 注册：[状态]
- tauri.conf.json 配置：[状态]
- updater.ts：[状态 + 行数]
- UpdateContext.tsx：[状态 + 行数]
- UpdateBanner.tsx：[状态 + 行数]
- 非 Tauri 环境兼容：[状态]

功能 2 — 启动错误 UI：
- Rust emit 事件：[状态]
- StartupErrorScreen.tsx：[状态 + 行数]
- 重试/查看日志功能：[状态]

功能 3 — 原生导出对话框：
- exportBookDesktop()：[状态]
- 导出调用点修改：[修改了哪些文件]
- 非 Tauri 环境兼容：[状态]

测试：
- Rust：[数量] passed
- cargo clippy：[状态]
- cargo fmt：[状态]
- 前端：[数量] passed（[新增数] 新增）
- pnpm build：[状态]
- 后端：[数量] passed
- ruff check：[状态]

改动文件列表：[...]
```
