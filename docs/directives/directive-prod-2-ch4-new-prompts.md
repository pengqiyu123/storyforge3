# PROD-2：ch4 生产（新提示词首验证）

> 指令编号：PROD-2
> 下发时间：2026-06-15
> 下发人：ZCode（PM）
> 执行人：Trae（首席开发主管）
> 优先级：P0（当前首要任务）

---

## 1. 问题陈述

ch1-ch3 均使用旧提示词生产（compose-v1 / plan-v1 / llm-audit-v1）。P-PROMPT-P0 + P-PROMPT-P1 已将提示词升级为 compose-v2 / plan-v2 / llm-audit-v2 / truth-extract-v2，但**新提示词尚未经过真实章节生产验证**。

ch4 是新提示词的**首次实战检验**。本指令的目标不是"写出一章好小说"，而是**验证新提示词能否端到端跑通全管线并产出可读章节**。

---

## 1.5 创作原则（本小说唯一核心主题）

> **"语言不是障碍，误解才是。而翻译，是最温柔的武器。"**

这句话是《别打了》的灵魂。每一章的剧情、冲突、人物行为都必须围绕这个主题展开或呼应。

具体含义：
- **语言不是障碍**：沈听澜的万声能力让他能听懂一切——兽人、精灵、器物、异兽、弯骨——但听懂不等于能化解冲突
- **误解才是**：各方势力因信息不对称、文化差异、利益冲突而互相误解，翻译暴露真相但也会激化矛盾
- **翻译是最温柔的武器**：沈听澜的翻译既是保护（让真相曝光），也是威胁（揭穿密令等于宣战），这个双刃性要贯穿始终

ch4 必须体现这条主线。沈听澜刚从"被动翻译工具"转变为"被众人注视的核心"，如何处理"翻译暴露真相后的代价"是 ch4 的核心张力。

---

## 2. 目标

1. 使用 agent/API 管线生产《别打了》第 4 章
2. 全管线跑通：plan → draft → audit → revise（如需）→ approve → truth-extract → export
3. 验证新提示词（compose-v2 / plan-v2 / llm-audit-v2 / truth-extract-v2）在真实生产中的表现
4. 产出 ch4 正文供人工读评

---

## 3. 执行步骤

### 3.0 前置条件

- **推送 P-PROMPT-P1**：`cd D:\python\Novel\storyforge3 && git push origin main`（commit ab6a230）
- **确认 backend 正常启动**：`python -m storyforge3` 或等效命令

### 3.1 生产管线

按分段管线依次执行：

```
Step 1: plan(book_id, chapter_no=4)
  → 使用 plan-v2 模板
  → 产出结构化计划（含钩子账）

Step 2: draft(book_id, chapter_no=4)
  → 使用 compose-v2 模板
  → truth_retriever 自动加载 ch1-ch3 truth 数据
  → 长度归一化（target_chars 按现有 book_meta 配置）

Step 3: audit(book_id, chapter_no=4)  [本地机械审计]
  → 运行 AuditRunner 全维度规则检查

Step 4: run_llm_audit(book_id, chapter_no=4, text)
  → 使用 llm-audit-v2 模板（10 维审计）
  → 检查是否有 critical 级别 issue

Step 5: 如有 critical/warning → revise(book_id, chapter_no=4)
  → 使用 revise-v1 模板
  → 重新审计确认通过

Step 6: approve(book_id, chapter_no=4)
  → 使用 truth-extract-v2 提取 truth
  → truth 保存到 truth/chapter-0004.json

Step 7: export(book_id, chapter_no=4)
  → 导出为 tomato_txt 格式
  → 状态推进到 EXPORTED
```

### 3.2 执行方式

**推荐通过 agent 模式（CLI）执行**：

```bash
# 在 storyforge3 目录下
python -m storyforge3 agent --book 别打了w帮你们翻译还不行吗_20260611 --chapter 4
```

或通过 API 分段调用（如果 agent 不可用）：

```bash
# 依次调用
POST /api/books/{book_id}/chapters/4/plan
POST /api/books/{book_id}/chapters/4/draft
POST /api/books/{book_id}/chapters/4/audit
# 如需修订
POST /api/books/{book_id}/chapters/4/revise
# 最后
POST /api/books/{book_id}/chapters/4/approve
POST /api/books/{book_id}/chapters/4/export
```

### 3.3 故障处理

- **plan/draft LLM 超时**：重试最多 2 次（P-FIX-3 已加 RemoteProtocolError retry）
- **draft 产出空内容或极短内容**：重试 draft，记录 LLM 响应日志
- **audit critical 通过不了**：revise 最多 2 轮，仍不过则保留草稿，上报 PM 处理
- **truth 提取失败**：重试 1 次，仍失败则手动检查 truth-extract-v2 prompt 输出
- **任何步骤失败**：保留已有中间产物（plan/draft/audit），不要 discard，上报 PM

---

## 4. 验收标准

### 4.1 管线完整性

- [ ] `chapter_states.json` 中 ch4 状态为 `exported`
- [ ] `chapters/0004.md` 存在且非空
- [ ] `truth/chapter-0004.json` 存在且 fact_assertions 非空
- [ ] 导出文件存在（tomato_txt 格式）

### 4.2 新提示词验证

- [ ] plan 输出包含"钩子账"段落（回收/推进/埋设）
- [ ] draft 正文字数在目标范围（book_meta chapter_word_count ±15%）
- [ ] llm_audit 输出包含 10 维度评估（JSON issues 列表）
- [ ] truth 输出的 hook_updates 包含 action 字段（planted/advanced/resolved）

### 4.3 连续性检查

- [ ] ch4 承接 ch3 结尾（弯骨石眼发声、灰眼转向沈听澜、众人注视沈听澜）
- [ ] ch4 未违背 ch1-ch3 truth 中的任何 fact_assertion
- [ ] ch4 未引入无来源的大设定、新势力或关键能力

### 4.4 质量（人工读评项，PM 后续检查）

以下项由 PM 亲自读 ch4 正文后判定：
- compose-v2 写作铁律执行情况（Show Don't Tell、情绪外化、五感代入）
- 去AI味检查（无"不是…而是…"、无破折号"——"、转折词不超频）
- 看点密集度（每 300 字至少 1 爽点、每 500 字至少 1 钩子）
- 断章是否在 action-climax（80/20 规则）

---

## 5. 不在本指令范围

- ❌ 不修改任何提示词模板（compose-v2 / plan-v2 / llm-audit-v2 已锁定）
- ❌ 不修改引擎代码（除非生产管线暴露引擎 bug）
- ❌ 不修改前端 UI
- ❌ 不做 ch5+ 生产（PROD-2 仅覆盖 ch4）

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| compose-v2 prompt 过长导致 LLM 截断 | 中 | draft 质量下降 | 如截断则分段生成或缩短 prompt |
| plan-v2 结构化输出解析失败 | 低 | plan 无法使用 | 检查 _extract_goal 是否兼容新格式 |
| llm-audit-v2 返回非 JSON | 低 | 审计无法解析 | LLMAuditor 已有 JSON 解析容错 |
| ch4 连续性断裂 | 中 | 可读性差 | truth_retriever 已加载 ch1-ch3 truth |
| LLM 服务不可用 | 低 | 生产中断 | 重试 + 等待恢复 |

---

## 7. 上报要求

生产完成后，Trae 必须汇报：

1. **管线执行日志**：每步执行结果（plan 输出摘要、draft 字数、audit 通过/失败、revise 轮数、truth 提取条数、export 路径）
2. **新提示词观察**：plan-v2 钩子账是否产出合理？compose-v2 写作铁律是否被 LLM 遵守？llm-audit-v2 10 维是否有新发现？
3. **异常记录**：任何重试、解析失败、截断等问题
4. **commit hash**：生产执行后如有状态文件变更需提交推送

---

## 附录 A：ch3 尾部上下文（ch4 必须承接）

ch3 结尾场景：
- 弯骨石眼睁开，发出古老干哑声音："能听见万声的人……你终于回到桥上了。"
- 赫鲁、伊芙蕾、商队头领、驿站守卫、秦缝、雾外灰眼——所有人同时看向沈听澜
- 沈听澜从"翻译工具人"变为"被多方注视的核心目标"

## 附录 B：ch3 truth 摘要（活跃钩子）

需回收/推进的钩子：
1. **灰木匣"买走的人正在笑"** — 内奸钩子，对象未揭露
2. **黑舌藤** — 暗门第二处痕迹，与夜灯仓火袭关联
3. **弯骨来历** — 灰白弯骨 + 裂封蜡 + 誓血 + 灰眼的关系未揭开
4. **灰眼威胁** — 已在驿站外，被血味/弯骨吸引，如何处理未解决
5. **"桥"与沈听澜身份** — 弯骨称沈听澜"终于回到桥上"，暗示深层过往

不可逆事实：
- 商队头领杀沈听澜命令已被当众翻译暴露
- 弯骨及裂封蜡已暴露在众人面前
- 灰眼已出现并转向沈听澜
- 沈听澜能听懂弯骨声音的事实已被关键人物注意到
