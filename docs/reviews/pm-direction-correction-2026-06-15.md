# PM 方向纠偏：回归小说生产本位（2026-06-15）

> 产品经理：Claude Code PM
> 触发：用户要求一轮"项目初衷 + 方向纠正"。两个输入——《章节按进度展示体验分析》（UX，已由 P-IMP-3b 落地）与 `TRAE_AGENT_CODE_WIKI.md`（核查发现是 **bytedance/trae-agent 软件工程 agent 的外部架构 wiki，与中文网文无关**，stray 在仓库根目录）。
> 状态：**本文为权威方向记录，凌驾 next.md 旧版**。后续一切计划以此为准。

---

## 1. 项目初衷（re-assert，不可漂移）

- StoryForge3 唯一存在的理由：**生产中文网文连载小说**（当前主力《别打了，我帮你们翻译还不行吗?》）。
- **引擎是仆，小说是主。** 一切引擎能力（管线 / truth / 审计 / Run Viewer / 门禁 / reconcile）都为"可持续产出高质量章节"服务。
- **成功度量 = 产出的小说**（章节数、质量、连续性、读者可读性），**不是**引擎特性数，**也不是**测试通过数。测试通过是手段，不是目的。

## 2. 方向漂移诊断

| 信号 | 证据 |
|------|------|
| 引擎过度精雕，小说停滞 | 自 P0.5（ch2 起草）以来 **7 个阶段全是引擎**（RunRecord / reconcile / dev 启动 / 章节显示 / Run Viewer / 门禁），《别打了》**仍停在 ch2**，ch3/ch4 是无正文幽灵产物 |
| 成功度量错位 | 近期验收清一色"566 passed + DOM 证据"，**鲜有"产出一章可读正文"** |
| 仓库范围蔓延 | 根目录混入 `inkos-master/`、`cc-switch-main/`、`TRAE_AGENT_CODE_WIKI.md` 等外部参考，核心（storyforge3 + 活跃小说）被淹没 |
| 计划把生产后置 | 旧 `next.md` 把小说生产推到"Phase 10B AutoDirector 之后"——**本末倒置**：AutoDirector 是"自动化产章"，不是"产章的前提" |

## 3. 纠正决策

1. **P1-3（门禁统一）是引擎工作的最后一项。** 之后**立即转入真实多章生产**。
2. **生产不依赖 AutoDirector。** agent-mode 下，agent（Claude Code / Codex）现在就能调 REST API 产章。AutoDirector 是把"人工驱动 agent 产章"自动化，**不是产章的前提**。
3. **成功度量切换**：下一里程碑 = **《别打了》产出 N 章可读正文**。验收含"人读得下去"（剧情/连续性/文笔），非仅"测试通过"。
4. **引擎扩张暂停（DEFER）**：P-IMP-2（导入 auto-verify）/ P-IMP-4（"运行全流程"标签）/ Phase 10B AutoDirector / 10C（RAG/方法论）**全部后置**，直到 dogfood 暴露**真实阻塞**才动。需求驱动，**不再 speculative 建特性**。
5. **幽灵章节 ch3/ch4 处置提上日程**：dogfood 前先定——**re-write**（重新产 ch3 正文）还是 **discard**（删孤儿 truth/export 产物）。reconcile 已给诊断，PM 验收后下 heal 决策（见 §6）。

## 4. 仓库范围澄清

| 类别 | 内容 | 处置 |
|------|------|------|
| **核心（主线）** | `storyforge3/`（活跃引擎）、`storyforge/`（生产工作区 + 活跃小说产物） | 一切开发在此 |
| **归档** | `storyforge2/`（396 tests，archived） | 只读参考，不动 |
| **外部参考** | `cc-switch-main/`、`docs/inkos-master/`、`调研报告/`、`experiment/`、`TRAE_AGENT_CODE_WIKI.md` | 借鉴源；**不混入主线**；明确标注"外部" |
| **跨项目规范** | `通用开发规范文件夹/`、`~/.claude/rules/` | 规范，非产品代码 |

> 规则：外部参考文档**不进** `storyforge3/docs/` 主线；放 `调研报告/` 或 `experiment/research/`，头部标"外部参考"。

## 5. 关于 TRAE_AGENT_CODE_WIKI.md

- 是 **bytedance/trae-agent（一个软件工程 agent：修 bug / 写代码）** 的架构 wiki，与中文网文生产**无关**。
- 可借鉴点（仅限未来 AutoDirector 设计时参考）：trajectory recording（SF3 已有 `pipeline.jsonl` + RunRecord，更强）、lakeview 步骤摘要、agent loop 模式。
- **StoryForge3 不是、也不应成为通用 agent 框架。** 它是网文生产引擎。不要让 trae-agent wiki 把项目方向拉向"造通用 agent"。
- **处置**：移至 `调研报告/trae-agent-architecture-wiki.md`，加头部"⚠ 外部参考（bytedance/trae-agent），非本项目"。

## 6. ch3/ch4 幽灵章节 heal 决策框架

reconcile（P-IMP-3b）已诊断：ch3/ch4 = `orphan`（有 truth+export，无正文/状态）。PM 决策框架：

| 选项 | 含义 | PM 倾向 |
|------|------|---------|
| **re-write** | 从 ch3 起重新产正文（沿用既有 truth 作上下文，或先 discard truth 再产） | ✅ 倾向：保留既有 truth/export 作"曾尝试"记录，重新跑 draft→audit→revise 补正文 |
| **discard** | 删 ch3/ch4 的 truth/export 孤儿产物，回到 ch2 干净状态续写 | 备选：若 truth 内容与重写冲突大则 discard |

**决策时机**：dogfood 启动前定。本纠偏不预设，留给 dogfood 第一步（先看 ch3/ch4 孤儿 truth 内容是否可用）。

## 7. 分析师输入规则（re-assert，纳入 pm-process）

- 分析师文档（Trae ×2、章节显示分析、trae-agent wiki）是 **INPUT**，PM 仲裁，**不直接成方向**。
- **代码行为类**主张必读源码核对（既定规则，两轮验证有效）。
- **外部项目 wiki** 仅作设计参考，**不触发"向该项目靠拢"**。

## 8. 文档更新清单（本轮已执行）

- 本文（方向纠偏权威记录）
- `next.md`：总方向改"小说生产本位"；P1-3 后转生产；10B/10C DEFER
- `storyforge3/CLAUDE.md`：加 North Star（项目初衷置顶）
- `current.md`：工作焦点对齐（P1-3 → 生产）
- `TRAE_AGENT_CODE_WIKI.md` → `调研报告/trae-agent-architecture-wiki.md` + 外部标注

## 9. 一句话

> **引擎已经够用，停手。下一里程碑不是又一个引擎特性，是《别打了》多出几章人读得下去的正文。**
