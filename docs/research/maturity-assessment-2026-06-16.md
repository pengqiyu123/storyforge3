# StoryForge3 项目成熟度评估

> 评估时间：2026-06-16
> 评估人：ZCode（PM）
> 评估方法：内部调研基准（5 个参考项目）+ 外部行业现状（联网搜索）+ 自身目标对标

---

## 一、成熟度判定

| 维度 | 评级 | 说明 |
|------|------|------|
| **引擎能力** | B（可用） | 真理系统+审计+修订+提示词 v2，能力组合领先行业 |
| **产品闭环** | C+（核心通） | 创建/删除/修改/恢复闭环已通，体验层粗糙 |
| **生产验证** | D+（刚起步） | 仅 4 章 dogfood，不足以暴露深层问题 |
| **工程质量** | B+（扎实） | 638+116 测试，~91% 覆盖，CI 全绿 |

**总判定：引擎就绪，生产验证不足。应转向连续生产。**

---

## 二、能力对标矩阵

### SF3 vs 竞品

| 能力 | SF3 | InkOS | ANWA | snowflake | 行业平均 |
|------|:---:|:-----:|:----:|:---------:|:--------:|
| 真理/连续性 | ✅ | ✅ | ✅ | ✅ | 🟡 |
| 机械审计 | ✅36 | ✅25 | ❌ | ✅ | 🟡 |
| LLM审计 | ✅10维 | ✅37维 | ✅6维 | ✅25维 | 🟡4-6维 |
| 钩子追踪 | 🟡摘要 | ✅账本 | ✅ | ✅5类型 | 🔴 |
| 看点密集度 | ✅ | ✅ | ❌ | ✅ | 🔴 |
| 断章规则 | ✅ | ✅ | ❌ | ✅ | 🔴 |
| 去AI味 | ✅ | ✅ | 🟡 | ✅ | 🟡 |
| 修订模式 | ✅5模式 | ✅双模 | ❌ | ❌ | 🔴 |
| MCP集成 | ✅15工具 | ❌ | ❌ | ❌ | 🔴 |
| AutoDirector | ❌ | ✅ | ✅ | ❌ | 🔴 |
| 实际产出 | ✅4章 | ❌ | ❌ | ❌ | 🔴 |

### SF3 领先项
1. **真理系统 + SQLite 持久化**——行业最大痛点（长篇连续性）的直接解决方案
2. **36 机械规则 + 10 维 LLM 审计**——审计深度超过大多数工具
3. **5 修订模式**——独有特性
4. **MCP 15 工具**——中文网文领域罕见
5. **4 章 dogfood 记录**——竞品普遍无公开产出

### SF3 短板
1. **钩子账本缺失**——truth 只存摘要，无 open/advance/resolve/defer 生命周期
2. **AutoDirector 缺失**——无法自动化生产，依赖人工驱动 agent
3. **提示词工程化不足**——Python 硬编码，无热重载/A-B 测试
4. **上下文优先级缺失**——固定 6 块，无 priority+dropOrder

---

## 三、行业现状（2026 年联网调研）

### AI 网文爆发但质量差
- 番茄/起点四成收稿来自 AI
- "48 小时 500 万字"极端案例出现
- **连续性断裂、套路化严重是行业共识痛点**

### SF3 的市场机会
- truth 系统直接解决连续性痛点
- 差异化定位正确：不是"更快地写"，而是"更长地保持一致"

### 学术基准（可对接）
- **WebNovelBench**（4000+ 中文网文，8 维 LLM-as-judge）
- **ConStory-Bench**（长篇一致性检测，Microsoft Research）
- **SCORE**（叙事不一致检测框架）

### 最接近竞品
- **InkOS**：TypeScript CLI + 5 agent + hook ledger + Studio UI，但无公开产出
- SF3 有 4 章 dogfood 记录是当前优势

---

## 四、决策：方向 A——连续生产验证

### 理由
1. 操作闭环已通，继续堆功能边际收益递减
2. 4 章不足以验证引擎真实能力，需 10+ 章暴露深层问题
3. 行业最大痛点（长篇连续性）正是 SF3 优势，需要用产出证明

### 行动计划
- 连续生产 ch5-ch15（10+ 章）
- 每章人工读评 + truth 连续性检查
- 暴露真实问题后按需补功能（方向 B/C 按需启动）

### 方向 B/C 保留（按需启动）
- **方向 B（补齐竞品差距）**：钩子账本 / AutoDirector / 提示词外部化——待生产暴露痛点后按需启动
- **方向 C（学术对接）**：WebNovelBench / ConStory-Bench——待有 10+ 章产出后建立客观质量基线

---

## 五、参考来源

- [WebNovelBench (arXiv 2505.14818)](https://arxiv.org/abs/2505.14818)
- [InkOS GitHub](https://github.com/Narcooo/inkos)
- [ConStory-Bench (Microsoft Research)](https://www.microsoft.com/en-us/research/publication/lost-in-stories-consistency-bugs-in-long-story-generation-by-llms/)
- [SCORE (arXiv 2503.23512)](https://arxiv.org/html/2503.23512v1)
- [awesome-llm-story-generation](https://github.com/Picrew/awesome-llm-story-generation)
- [The AI Agents Stack 2026 (O'Reilly)](https://www.oreilly.com/radar/the-ai-agents-stack-2026-edition/)
