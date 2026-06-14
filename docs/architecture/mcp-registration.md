# StoryForge3 MCP Server - Claude Code 注册指南

本文档说明如何把本地 StoryForge3 MCP Server 注册到 Claude Code。StoryForge3 当前通过 stdio 启动，入口为 `python -m storyforge3.mcp`。

## 快速注册

在 StoryForge3 项目目录外或目录内均可运行：

```bash
claude mcp add storyforge3 -- python -m storyforge3.mcp
```

如果你的默认 `python` 不是 StoryForge3 所在虚拟环境，请改用虚拟环境中的 Python 绝对路径，例如：

```bash
claude mcp add storyforge3 -- D:\python\Novel\storyforge3\.venv\Scripts\python.exe -m storyforge3.mcp
```

## 手动配置

如果需要手动配置，可将以下片段加入项目级 `.claude/settings.json`：

```json
{
  "mcpServers": {
    "storyforge3": {
      "command": "python",
      "args": ["-m", "storyforge3.mcp"],
      "cwd": "D:\\python\\Novel\\storyforge3"
    }
  }
}
```

如果使用虚拟环境绝对路径：

```json
{
  "mcpServers": {
    "storyforge3": {
      "command": "D:\\python\\Novel\\storyforge3\\.venv\\Scripts\\python.exe",
      "args": ["-m", "storyforge3.mcp"],
      "cwd": "D:\\python\\Novel\\storyforge3"
    }
  }
}
```

`cwd` 应指向 StoryForge3 项目根目录，也就是包含 `pyproject.toml`、`src/` 和 `books/` 的目录。

## 验证

注册后重启 Claude Code，然后让 Claude Code 调用只读工具：

```text
请调用 storyforge3 的 list_books 查看当前工作区中的书籍。
```

如果返回书籍列表或空列表，说明 MCP Server 已连接成功。空列表是有效结果，不代表失败。

也可以在终端中先验证入口是否能启动：

```bash
python -m storyforge3.mcp
```

该命令会启动 stdio MCP Server，通常不会打印交互式提示；确认没有立刻报错即可。

## 工具速查表

| Tool | 用途 | 属性 | 建议下一步 |
|------|------|------|------------|
| `list_books` | 列出工作区中的所有书籍，返回 ID、标题、类型、状态和进度。 | 只读；不调用 LLM。 | 用 `get_book` 查看详情，或用 `create_book` 创建新书。 |
| `get_book` | 获取指定书籍的详细信息。 | 只读；不调用 LLM。 | 根据状态继续 `build_world`、`plan_chapter` 或 `draft_chapter`。 |
| `create_book` | 创建新书并初始化书籍配置。 | 创建；不调用 LLM。 | 调用 `build_world` 构建世界观，再用 `create_character` 创建角色。 |
| `build_world` | 根据类型和种子描述生成世界观、力量体系、核心冲突和规则。 | 创建；调用 LLM。 | 调用 `create_character` 创建角色，或进入 `plan_chapter`。 |
| `create_character` | 用自然语言描述生成并保存角色档案。 | 创建；调用 LLM。 | 继续创建更多角色，或用 `list_characters` 检查角色列表。 |
| `list_characters` | 列出指定书籍中的所有角色。 | 只读；不调用 LLM。 | 确认角色齐备后调用 `plan_chapter`。 |
| `plan_chapter` | 为指定章节生成目标、卷纲节点、必须保留和必须避免。 | LLM 调用；可能耗时数分钟。 | 调用 `draft_chapter` 起草正文。 |
| `draft_chapter` | 自动规划并起草指定章节正文。 | LLM 调用；可能耗时 2-5 分钟。 | 调用 `audit_chapter` 审计质量。 |
| `audit_chapter` | 运行章节审计并返回通过状态、阻断问题数和警告数。 | 只读；调用 LLM。 | 通过后可 `export_book`；未通过则 `revise_chapter`。 |
| `revise_chapter` | 根据审计结果修订章节，支持 `auto`、`polish`、`spot_fix`、`anti_detect`、`surgical`、`rework`。 | 修改；调用 LLM；可能耗时数分钟；`rework` 为全文重写。 | 再次调用 `audit_chapter`，建议最多修订 2 轮。 |
| `get_chapter_status` | 查询章节状态、标题和是否已有正文。 | 只读；不调用 LLM。 | 根据返回状态选择 `draft_chapter`、`audit_chapter` 或 `revise_chapter`。 |
| `export_book` | 将书籍导出为 `tomato_txt`、`md`、`epub` 或 `qidian_txt`。 | 创建；不调用 LLM。 | 检查导出路径，或继续起草下一章。 |
| `run_short_story` | 一键执行短篇规划、起草、审计、修订和导出。 | 修改；LLM 调用；可能耗时 10-30 分钟。 | 用 `get_short_story_status` 查询最终状态和错误信息。 |
| `get_short_story_status` | 查询短篇状态、是否有正文和当前字符数。 | 只读；不调用 LLM。 | 若失败，查看 `error`；若完成，检查导出结果。 |
| `get_truth` | 获取最新 truth 连续性数据，包括事实断言、角色变化和不可逆事实。 | 只读；不调用 LLM。 | 用于理解跨章连续性；后续 `draft_chapter` 会自动使用上下文。 |

## 推荐工作流

### 长篇逐章流程

```text
create_book -> build_world -> create_character -> list_characters
-> plan_chapter -> draft_chapter -> audit_chapter
-> revise_chapter(如未通过) -> audit_chapter -> export_book
```

示例请求：

```text
创建一本番茄都市长篇，书名《我是路人甲》，目标 100 章，每章 2500 字。
然后基于“近未来都市 + 存在感系统 + 异常机构”构建世界观。
```

### 短篇一键流程

```text
create_book -> run_short_story -> get_short_story_status
```

示例请求：

```text
创建一本恐怖短篇《深夜便利店》，目标 1 章 8000 字，然后运行短篇全流程。
```

## 故障排查

### Python 路径不正确

现象：Claude Code 报 `python` 找不到，或找不到 `storyforge3` 模块。

处理：

```bash
where python
python -c "import storyforge3; print(storyforge3.__file__)"
```

如果导入失败，把注册命令或 `settings.json` 的 `command` 改为 `.venv\Scripts\python.exe` 的绝对路径。

### 工作目录不正确

现象：Server 能启动，但找不到项目配置、书籍目录或写入位置异常。

处理：确认 `settings.json` 中的 `cwd` 是 StoryForge3 项目根目录：

```text
D:\python\Novel\storyforge3
```

该目录应包含 `pyproject.toml`、`src/`、`docs/` 和 `books/`。

### 依赖未安装

现象：启动时报 `ModuleNotFoundError`，例如缺少 `mcp`、`pydantic` 或项目依赖。

处理：

```bash
cd D:\python\Novel\storyforge3
python -m pip install -e .
```

如果项目使用虚拟环境，先激活：

```bash
D:\python\Novel\storyforge3\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### 如何验证修复

1. 在终端运行 `python -m storyforge3.mcp`，确认没有立刻报错。
2. 重启 Claude Code，让它调用 `list_books`。
3. 若 `list_books` 返回空列表或书籍列表，注册成功。
4. 若涉及 LLM 工具失败，先用只读工具确认连接正常，再检查 LLM 相关环境变量和项目配置。
