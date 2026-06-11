# Codex 指令：Phase 7D-1 — CI/CD + 签名

> 发出日期：2026-06-10
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 7C 完成（436 后端 tests + 59 前端 tests, ruff clean）

---

## 任务概述

建立 GitHub Actions CI/CD 流水线，实现推送 tag 自动构建、签名和发布 Tauri 桌面应用。

**当前状态**：
- 无 `.github/` 目录，无任何 CI/CD
- `src-tauri/tauri.conf.json` 配置了 updater endpoint 但缺 `pubkey` 和 `createUpdaterArtifacts`
- `pyproject.toml` 有 `[project.optional-dependencies] dev` 组
- `src-tauri/Cargo.toml` release profile 已优化（LTO thin, strip symbols）
- GitHub 仓库：`pengqiyu123/storyforge3`（tauri.conf.json 中 updater endpoint 已指向此仓库）

**核心决策**：
1. **Windows-only 初期** — 无 Apple Developer 账号，macOS/Linux 构建延后
2. **自签名 Tauri key** — 不是 Windows 代码签名证书，仅用于 Tauri updater 签名验证
3. **Python 不打包** — Tauri 二进制仅包含前端 + Rust 壳，运行时需要系统 Python + `pip install storyforge3`
4. **tauri-apps/tauri-action** — 官方 action 处理构建、签名和 release 上传

---

## Part 1：CI Workflow

### 1.1 创建 `.github/workflows/ci.yml`

三个 job 并行运行：

**Job 1 — backend**：
```yaml
runs-on: ubuntu-latest
steps:
  - checkout
  - setup-python 3.11
  - pip install -e ".[dev]"
  - ruff check .
  - pytest tests/ -q
```

**Job 2 — frontend**：
```yaml
runs-on: ubuntu-latest
steps:
  - checkout
  - pnpm/action-setup@v4
  - setup-node 20 (cache: pnpm)
  - pnpm --dir web install --frozen-lockfile
  - pnpm --dir web test
  - pnpm --dir web build
```

**Job 3 — desktop**：
```yaml
runs-on: ubuntu-latest
steps:
  - checkout
  - pnpm/action-setup@v4
  - setup-node 20 (cache: pnpm)
  - pnpm --dir web install --frozen-lockfile
  - pnpm --dir web build
  - dtolnay/rust-toolchain@stable
  - apt-get install libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf
  - cargo check --manifest-path src-tauri/Cargo.toml
```

**触发条件**：push to main + PR to main。**并发控制**：同分支 cancel in-progress。

**参考**：CC-Switch `.github/workflows/ci.yml`（结构、缓存、并发控制）。

---

## Part 2：Release Workflow

### 2.1 创建 `.github/workflows/release.yml`

**触发条件**：`push tags: ['v*']`

**策略**：仅 Windows 矩阵（`windows-2022`）。

```yaml
name: Release
on:
  push:
    tags: ['v*']
permissions:
  contents: write
concurrency:
  group: release-${{ github.ref_name }}
  cancel-in-progress: true

jobs:
  release:
    runs-on: windows-2022
    steps:
      - checkout
      - pnpm/action-setup@v4
      - setup-node 20 (cache: pnpm)
      - pnpm --dir web install --frozen-lockfile
      - pnpm --dir web build
      - dtolnay/rust-toolchain@stable
      - uses: tauri-apps/tauri-action@v0
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}
          TAURI_SIGNING_PRIVATE_KEY_PASSWORD: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY_PASSWORD }}
        with:
          tagName: ${{ github.ref_name }}
          releaseName: 'StoryForge3 ${{ github.ref_name }}'
          releaseBody: 'See assets to download.'
          releaseDraft: false
          prerelease: true

  assemble-latest-json:
    runs-on: ubuntu-latest
    needs: release
    permissions:
      contents: write
    steps:
      - Download release assets (.msi + .sig)
      - Generate latest.json (version, pub_date, windows-x86_64 signature + url)
      - Upload latest.json to release
```

**latest.json 格式**（仅 Windows，参考 CC-Switch `release.yml:565-660` 的 shell 逻辑，简化为 Windows-only）：

```json
{
  "version": "0.1.0",
  "notes": "Release v0.1.0",
  "pub_date": "2026-06-10T00:00:00Z",
  "platforms": {
    "windows-x86_64": {
      "signature": "<from .msi.sig>",
      "url": "https://github.com/pengqiyu123/storyforge3/releases/download/v0.1.0/StoryForge3_0.1.0_x64_en-US.msi"
    }
  }
}
```

**注意**：`tauri-apps/tauri-action` 自动处理构建和上传，但 latest.json 需要手动组装（因为 Windows-only 不需要 CC-Switch 的多平台合并逻辑，但需要单独生成 latest.json 以供 updater 使用）。

如果 `tauri-apps/tauri-action` 已自动生成 latest.json（当 `createUpdaterArtifacts: true` 时），则 `assemble-latest-json` job 可简化为仅验证 latest.json 已上传。

---

## Part 3：Tauri 签名配置

### 3.1 更新 `src-tauri/tauri.conf.json`

```jsonc
{
  "bundle": {
    "active": true,
    "targets": "all",
    "createUpdaterArtifacts": true,  // 新增
    // ... 其余不变
  },
  "plugins": {
    "updater": {
      "pubkey": "<PLACEHOLDER>",  // 新增：运行 tauri signer generate 后填入
      "endpoints": [
        "https://github.com/pengqiyu123/storyforge3/releases/latest/download/latest.json"
      ]
    }
  }
}
```

### 3.2 签名密钥生成文档

**新文件**：`docs/release-setup.md`

内容：

```markdown
# StoryForge3 发布设置

## 首次设置（一次性）

### 1. 生成 Tauri 签名密钥

```bash
pnpm tauri signer generate -w ~/.tauri/storyforge3.key
```

命令会输出：
- 公钥（一行 base64）→ 复制到 `src-tauri/tauri.conf.json` 的 `plugins.updater.pubkey`
- 私钥（写入 `~/.tauri/storyforge3.key`）

### 2. 配置 GitHub Secrets

在 GitHub 仓库 Settings → Secrets and variables → Actions 中添加：

| Secret 名称 | 值 |
|-------------|-----|
| `TAURI_SIGNING_PRIVATE_KEY` | 私钥文件的完整内容（两行文本）|
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | 生成时设置的密码（如果设置了）|

### 3. 验证

推送 `v0.1.0` tag 触发 release workflow：
```bash
git tag v0.1.0
git push origin v0.1.0
```

检查 GitHub Actions 是否成功构建并发布。
```

---

## Part 4：借鉴来源

| 借鉴内容 | 来源文件 | 行数 | 借鉴方式 |
|---------|---------|------|---------|
| **CI workflow 结构** | CC-Switch `.github/workflows/ci.yml` 全文 | ~80 行 | **骨架移植**：3-job 并行结构、缓存策略、并发控制，替换为 SF3 的 Python+pnpm+Rust 命令 |
| **Release workflow 结构** | CC-Switch `.github/workflows/release.yml:1-30` (触发+矩阵) | ~30 行 | **骨架移植**：tag 触发、matrix strategy，简化为 Windows-only |
| **Tauri signing key 处理** | CC-Switch `.github/workflows/release.yml:97-151` | ~54 行 | **直接复用**：3 种密钥格式检测逻辑完整移植 |
| **latest.json 组装** | CC-Switch `.github/workflows/release.yml:565-660` | ~95 行 | **模式复用**：shell 脚本遍历 .sig 文件生成 JSON，简化为 Windows-only |
| **tauri.conf.json updater 配置** | CC-Switch `src-tauri/tauri.conf.json` bundle + plugins 段 | ~20 行 | **直接复用**：`createUpdaterArtifacts`、`pubkey` 字段格式 |

**新写比例**：约 **25%**。CI/CD YAML 骨架从 CC-Switch 移植，SF3 特有的部分：Python backend CI job、简化为 Windows-only 的 release 矩阵、release-setup.md 文档。

### 移植适配清单

| 源项目原始 | SF3 适配 |
|-----------|---------|
| CC-Switch CI 用 `pnpm install --frozen-lockfile`（根目录有 lockfile） | SF3 改为 `pnpm --dir web install --frozen-lockfile`（monorepo，web 子目录有 lockfile） |
| CC-Switch release 4 平台矩阵（Windows/Linux/macOS ARM） | SF3 仅 Windows（无 Apple Developer，无 Linux 需求） |
| CC-Switch `cargo build` 在根目录 | SF3 改为 `cargo check --manifest-path src-tauri/Cargo.toml` |
| CC-Switch `latest.json` 包含 darwin/windows/linux 4 个目标 | SF3 仅 `windows-x86_64` |
| CC-Switch 产品名 "CC Switch" | SF3 改为 "StoryForge3" |

---

## 验收标准

### CI Workflow

- [ ] `.github/workflows/ci.yml` 存在，3 个 job（backend / frontend / desktop）
- [ ] backend job 运行 ruff + pytest（436 tests）
- [ ] frontend job 运行 pnpm test + pnpm build
- [ ] desktop job 运行 cargo check
- [ ] 触发条件：push main + PR main
- [ ] 并发控制：同分支 cancel in-progress

### Release Workflow

- [ ] `.github/workflows/release.yml` 存在，触发条件为 `v*` tag
- [ ] Windows 矩阵构建 Tauri 二进制
- [ ] 使用 `tauri-apps/tauri-action`
- [ ] 构建产物上传到 GitHub Releases
- [ ] `assemble-latest-json` job 生成 latest.json 并上传

### Tauri 配置

- [ ] `tauri.conf.json` 添加 `createUpdaterArtifacts: true`
- [ ] `tauri.conf.json` 添加 `pubkey` 字段（值可以是占位符，文档说明如何替换）
- [ ] `docs/release-setup.md` 包含密钥生成和 GitHub Secrets 配置说明

### 质量

- [ ] YAML 语法正确（可用 `actionlint` 或在线验证）
- [ ] 现有 436 tests 不退步（CI workflow 会验证）

---

## 估算工作量

| 部分 | 文件 | 预估行数 |
|------|------|---------|
| CI workflow | `.github/workflows/ci.yml` | ~60 行新增 |
| Release workflow | `.github/workflows/release.yml` | ~100 行新增 |
| tauri.conf.json 修改 | `src-tauri/tauri.conf.json` | ~3 行改动 |
| 签名设置文档 | `docs/release-setup.md` | ~40 行新增 |
| **合计** | **4 个文件** | **~200 行** |

---

## 不做的事（Out of Scope）

- ❌ 不做 macOS 构建/签名/公证（无 Apple Developer 账号）
- ❌ 不做 Linux 构建（AppImage/deb/rpm）
- ❌ 不做 Python 打包嵌入 Tauri（远期目标）
- ❌ 不做 Windows EV 代码签名证书（仅自签名 updater key）
- ❌ 不做 Dependabot 配置
- ❌ 不做 Claude Review workflow
- ❌ 不改 Rust 代码
- ❌ 不改 Python 代码
- ❌ 不改前端代码
