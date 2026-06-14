# PM 综合决策汇总：Trae 两轮分析 + PM 两轮判断（2026-06-14）

> 产品经理：Claude Code PM
> 职责：把第三方分析师 Trae 的两轮报告与 PM 两轮判断合并为**单一权威记录**，作为后续指令的事实依据。不重复源文档内容，只交叉引用 + 裁决。
> 更新时间：2026-06-14

## 源文档

| 文档 | 内容 |
|------|------|
| [codex-current-status.md](codex-current-status.md) | **Trae 第一轮**：Codex 状态 / P0.5 / P1-1 / 《别打了》数据分析（Trae §1–§9）+ PM §A–§G 判断 |
| [trae-ccswitch-import-diff-analysis.md](trae-ccswitch-import-diff-analysis.md) | **Trae 第二轮**：CC-Switch 导入失败差异分析（vs Auto-news2） |
| [pm-analysis-import-and-chapter-flow.md](pm-analysis-import-and-chapter-flow.md) | **PM 第一轮**：对 Trae 第二轮的逐条裁决 + 模型导入设计 + 章节显示 + 用户流程重设计 |
| 本文 | **PM 第二轮**：两轮合并裁决 + 事故记录 + 路线图 |

---

## 1. 两轮分析师输入定位

| 轮次 | Trae 主题 | PM 整体评价 | 关键修正 |
|------|----------|------------|---------|
| 第一轮 | Codex 状态 / P0.5 / P1-1 / 《别打了》数据 | ⭐⭐⭐⭐ 数据洞察有价值，两处风险误判 | truth 未来泄露 **高→低**；幽灵章节 **升级**；P1-1 范围收口 |
| 第二轮 | CC-Switch 导入失败差异（vs Auto-news2） | ⭐⭐⭐⭐ 后端配置分析扎实，一处假阳性 P0 | P0-3 前端 envelope **证伪**；providers.json 实际存在（非彻底失败） |

---

## 2. PM 逐轮裁决（合并）

### 第一轮关键裁决（详见 codex-current-status.md §A–§G）

- 主线 agent-mode-only：**方向成立**
- P0.5 已完成：**属实**
- P1-1 进入：**接受**，附 3 条 PM 约束（reconciliation 硬验收 / truth 防御测试 / book.json 不混入提交）
- truth retriever 未来泄露风险：**高 → 低**（`retriever.py:49/56/64` 已有 `< chapter_no` 过滤）
- 幽灵章节 ch3/ch4：**升级**为首要真实用例

### 第二轮关键裁决（详见 pm-analysis-import-and-chapter-flow.md §1）

| Trae 主张 | PM 裁决 | 已落地? |
|-----------|---------|---------|
| P0-1 providers_config_dir 相对路径依赖 cwd | ✅ 确认 | ✅ Codex 锚定项目根（`config.py` `resolved_providers_config_dir`） |
| P0-2 .env 死配置（CCSWITCH_* 被吞） | ✅ 确认 | ✅ Codex 加 `ccswitch_db_path` 字段 + 生效 |
| P0-3 前端读 raw response 致列表空 | ❌ **证伪** | — `client.ts` 已解包 `envelope.data`，前端是对的 |
| P1-4 火山 `/api/coding` 不剥离 | ✅ 已修（Trae 正确） | ✅ 既有 + builder/route-candidate 测试 |
| P1-5 无 key provider 被展示 | ✅ 确认 | ✅ 前端禁选 + 后端 `NO_IMPORTABLE_PROVIDER` |

---

## 3. Trae 分析模式（PM 复盘 → 规则）

Trae 两轮各出现一次"**断言代码行为但未读源码**"：

- 第一轮：truth 泄露"高风险"（实为低，`retriever.py` 已过滤）
- 第二轮：前端 envelope"不匹配"（实为正确，`client.ts` 已解包）

> **PM 规则（纳入 pm-process）**：对 Trae 的"**代码行为类**"主张，PM 必须 Read 源码核对后再采信；Trae 的"**数据状态 / 配置文件 / 环境变量**"类主张可直接采信（这两类两轮均准确）。

---

## 4. 事故记录：后端未运行（2026-06-14）

- **现象**：网页能打开但报错 + 《别打了》"消失"
- **根因**：**FastAPI 后端 `:8000` 未运行**，Vite `:5173` 代理到死端口 → 所有 `/api/*` 失败 → 空列表 + 报错。**非代码 bug，非数据丢失。**
- **验证**：PM 直跑数据层 `BOOK COUNT=1`（书可发现）；代码 545 tests / reconcile 输出正确；`project_root` 解析正确、providers.json/ccswitch.db 均在
- **处置**：PM 起 `storyforge3 serve :8000` → health / books / providers 全恢复，书立即回来
- **教训**：这是**第二次**同因事故（前次"页面打不开"同根因）。**缺统一启动入口** → 下发指令 **P-OPS-1**

---

## 5. 已完成（截至 2026-06-14）

| 项 | 状态 | 证据 |
|----|------|------|
| P1-1 RunRecord 后端闭环 | ✅ | 532 passed |
| **P1-1b 章节产物一致性诊断 + truth 防御** | ✅ **本轮验收通过** | 545 passed；reconcile 对《别打了》输出 ch3/4 inconsistent（`export_without_state`+`export_without_text`+`truth_without_state`）、ch1/2 consistent；truth retriever 严格 `< 目标章` 测试 |
| **P-IMP-1 provider 配置健壮性** | ✅ Codex 在 `e0e020b` 一并落地 | 路径锚定项目根 + `CCSWITCH_DB_PATH` 生效 + 无 key 前端禁选 + 火山 builder/route 测试 |

---

## 6. 指令路线图（剩余）

| 优先级 | 指令 | 状态 | 依赖 |
|--------|------|------|------|
| **P0** | **P-OPS-1 统一启动入口** | 🆕 **本轮下发** | — |
| P1 | P-IMP-3 章节列表读 reconcile（"5 章"启发式修复） | 待发 | P1-1b ✅ |
| P1 | P-IMP-2 导入 UX 余项（auto-verify + 错误码分层） | 待发 | — |
| P2 | P-IMP-4 agent-mode UI 清理（"运行全流程"标签等） | 待发 | — |

---

## 7. 数据安全声明

《别打了》全部产物（chapters / truth / exports / state / runs）+ `.storyforge3/providers.json` + `~/.cc-switch/cc-switch.db` 均**完整未损**（2026-06-14 PM 直跑数据层确认 `BOOK COUNT=1`）。幽灵章节 ch3/ch4 仍按 P1-1b 红线**只诊断不 heal**，等 PM 验收 reconcile 准确性后决定。

---

## 8. 待用户确认（悬而未决，不阻塞 P-OPS-1）

1. providers.json 落**项目根** vs `%APPDATA%/StoryForge3`？—— PM 倾向项目根（Codex 已按此落地）。
2. 世界/角色/卷纲"构建"按钮**保留为手动 Setup 面**？—— PM 倾向保留。
3. 章节 heal（清理 ch3/ch4 幽灵产物）时机？—— 等 P-IMP-3 前端能可视化不一致后再决定。
