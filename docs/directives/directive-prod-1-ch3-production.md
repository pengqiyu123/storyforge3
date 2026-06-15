# 指令 PROD-1：《别打了》ch3 真实生产（引擎闭环验证 + 小说产出）

> 下发 Codex。前置：P1 全部闭环 ✅ / P-DISCARD-1 ✅ / ch3/4 幽灵已清理 ✅。
> 依据：[`pm-direction-correction-2026-06-15.md`](../reviews/pm-direction-correction-2026-06-15.md)——**引擎已够用，停手；下一里程碑 = 《别打了》多出几章人读得下去的正文。**
> 性质：本指令**不是引擎特性开发**，是**生产执行**——用现有引擎通过 API 实际产出一章可读正文。

## 背景

《别打了》停在 ch2（approved，truth 已提取）。ch2 结尾：巡夜队查仓、灰木匣说"他们之中，有一个已经被买走了"、沈听澜被赫鲁和伊芙蕾夹着往暗门走。reconcile 状态干净（max=2/valid=2/next_writable=3），引擎 ready。

**本指令目标**：通过 `POST /api/books/{book_id}/chapters/3/run` 全管线产 ch3 正文，验证引擎端到端闭环，产出人读得下去的章节。

## 任务

### 1. ch2 补全：approve → truth 提交 → export

当前 ch2 状态为 `approved`（truth 已提取但未提交到 TRUTH_COMMITTED，也未 export）。在产 ch3 前，先闭环 ch2：

```
ch2 当前状态：approved
→ POST /chapters/2/approve（幂等，应推进到 truth_committed）
→ POST /chapters/2/export（fmt=tomato_txt）
→ 验证 reconcile ch2 状态变为 exported
```

若 `approve` 已幂等返回 `truth_committed`（`_advance_approve_state` 双跳），则直接 `export`。

### 2. ch3 全管线生产

```
POST /api/books/别打了w帮你们翻译还不行吗_20260611/chapters/3/run
```

全管线 7 阶段（plan → draft → audit → revise → approve → truth → export），使用**真实 provider**（火山引擎 ark-code-latest）。

**ch3 剧情方向参考**（PM 建议轮廓，agent 可根据 truth 召回 + 世界观 + 角色关系发挥）：

- **承上**：ch2 结尾沈听澜被夹往暗门，灰木匣贴胸口说"有人被买走了"。巡夜队查仓封存中。
- **ch3 核心场景**：秤房公开验封——三方（赫鲁/伊芙蕾/秦缝）+ 沈听澜在巡夜队监管下刮末称验灰木匣。此过程应暴露更多灰木匣的秘密，同时推进秦缝嫌疑线。
- **角色互动**：沈听澜继续在威胁下翻译，但逐步从"被动人质"转为"不可或缺的证人"，展现翻译能力的价值。赫鲁和伊芙蕾继续敌对但被迫合作。
- **新信息**：灰木匣内容物或验封结果揭示更大线索（南枝契网络？灰木匣自身性质？）。梁上袭击者/铜环怪物的后续。
- **钩子**：ch3 结尾留悬念——新危机或新角色引入，驱动 ch4。
- **字数目标**：2000-3000 中文字。

### 3. ch3 产物验证

全管线完成后逐项检查：

```powershell
# reconcile 验证
# 期望：max_chapter=3, valid_chapter_count=3, ch3 status=exported, no inconsistencies

# 正文文件存在且非空
# plans/0003.json 存在
# truth/chapter-0003.json 存在（truth 提取完成）
# exports/chapter-0003.* 存在
# state/chapter_states.json 含 ch3 exported

# truth 召回验证
# 新 ch3 truth 条目与 ch1/ch2 truth 不矛盾
# ch1/ch2 hook 中的伏笔被合理延续或推进
```

### 4. SSE 进度监控

run 期间 SSE 应实时推送：
- `run:start` → `stage:start(plan)` → `stage:complete(plan)` → ... → `run:complete`
- draft 阶段应有 `llm:progress` + `llm:chunk` 流式事件

若 SSE 中断或超时，记录现象但不阻塞——run 后台仍继续，可通过 `GET /run` 恢复状态。

### 5. 失败处理

若任何阶段失败（provider 超时 / LLM 错误 / 审计 blocking）：

- **plan/draft 失败**：检查 provider 连通（`storyforge3 health`），重试 `POST /run`。
- **audit blocking > 0**：检查 blocking issues 内容。若为可修订问题（文风/AI 痕），自动 `revise` 后重跑 audit→approve→truth→export。若为结构性问题（剧情硬伤），**回报 PM 裁决**，不擅自 continue。
- **truth 提取失败/超时**：重试 `POST /chapters/3/run` 从 `resume_from=truth` 恢复。
- **任何阶段反复失败（3 次以上）**：**回报 PM**，附带错误信息 + 正文内容 + audit 结果，PM 判断是否 accept 或 discard 重产。

## 真实生产约束

- **使用真实 provider（火山 ark-code-latest）**。不用 fake provider。
- **不动引擎代码**。本指令是纯生产执行，不改 `src/` 下任何文件。发现引擎 bug 则记录但不修。
- **不动 prompt 模板**。用现有 prompt 配置，不优化。
- **若引擎能力不足导致产出质量差**：这是**预期内暴露的真实阻塞**，记录具体问题（如：truth 召回遗漏、上下文不足、文风不对），回报 PM 开新指令解决。

## 回报

逐项回报：

1. **ch2 闭环结果**：approve/export 后 reconcile 状态。
2. **ch3 run 记录**：`GET /run` 的完整 JSON（含各阶段耗时、状态）。
3. **ch3 正文全文**：`chapters/0003.md` 内容。
4. **ch3 truth**：`truth/chapter-0003.json` 内容（PM 人工审核连续性）。
5. **ch3 审计结果**：blocking/warning 数量和类型。
6. **reconcile 最终状态**：全书一致性。
7. **SSE 事件序列**（若有异常则标注）。
8. **生产过程遇到的问题**（provider 超时、重试次数、质量观察等）。

## 验收标准（PM 人工读评）

- ✅ ch3 正文人读得下去（非 fake provider、非重复模板）
- ✅ 剧情与 ch1/ch2 连续（角色一致、事件承接、truth 无矛盾）
- ✅ 全管线 7 阶段完成（exported）
- ✅ reconcile 干净（无 inconsistent、无孤儿产物）
- ✅ truth 提取有意义（非空、非幻觉）
- ✅ 无新幽灵产物

## 红线

- ❌ **禁止使用 fake provider / mock provider 产正文**——必须真实 LLM 输出。
- ❌ **禁止修改引擎代码**——纯生产执行，不改 `src/`。
- ❌ **禁止跳过 audit/truth/export**——全管线 7 阶段完整闭环。
- ❌ **禁止不动《别打了》以外的真实数据**。
- ❌ **禁止在产出质量明显有问题时强行继续**——回报 PM 裁决。

## Out of Scope

- ❌ ch4 生产（本指令只产 ch3，ch4 待 ch3 验收后）。
- ❌ 引擎特性修改（发现 bug 只记录，不修）。
- ❌ prompt 优化（用现有配置）。
- ❌ 前端改动。
- ❌ AutoDirector / 批量产章。
