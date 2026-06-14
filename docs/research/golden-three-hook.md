# 调研报告：网文开篇钩子检测与 golden_three_hook 规则重设计

> 日期：2026-06-07
> 触发：E2E 测试 Ch3 `revision_exhausted`，post-mortem 发现规则误判有效钩子
> 目的：为 `golden_three_hook` 审计规则重写提供理论和实践依据

## 1. 问题背景

### 当前规则

```python
# src/storyforge3/audit/rules.py:51-54
def check_golden_three_hook(ctx: MechanicalContext) -> RuleResult:
    head = "\n".join(ctx.paragraphs[:3])
    passed = any(marker in head for marker in ("突然", "不对", "异常", "发现", "声音", "门"))
    return make_result("golden_three_hook", passed, RuleSeverity.BLOCKING, RuleCategory.STRUCTURE, "前三段缺少有效钩子")
```

### 误判案例

第 3 章开头：

> 林默的名字，正被墙里的人一下一下敲掉。
> 叩，叩叩。
> 第三下落下，白墙猛地向外鼓起，顶出一枚掌印，正按在林默胸口的位置。

这个开头悬念强、画面感强、节奏利落，但不含 6 个关键词中的任何一个，被判定为 blocking failure。经两轮 SPOT_FIX 修订后仍未加入指定关键词，触发 `revision_exhausted`。

### 规则缺陷

| 缺陷 | 详情 |
|------|------|
| 关键词来源不明 | 无文档、无测试、无参考依据，疑似工程占位 |
| 表达力不足 | 只检测 6 个词，无法识别短句冲击、动作画面、悬念模式 |
| 误判风险高 | 有效钩子被误判为失败，浪费修订轮次 |
| 分类不一致 | 生产规则 `RuleCategory.STRUCTURE`，revision_modes 映射为 `"style"` |

## 2. 调研来源

| 来源 | 类型 | 核心贡献 |
|------|------|----------|
| snowflake-fiction 本地参考 | 写作理论框架 | 五类钩子系统 + 开篇通过标准 + 钩子密度量化 |
| oh-story-claudecode (GitHub) | 开源项目 | 章首钩子 7 式 + 前 500 字设计 + 黄金三章策略 |
| WebNovelBench (arXiv 2025) | 学术论文 | 8 维度网文质量评估 + LLM-as-Judge 方法论 |
| 知乎/网文社区讨论 | 行业知识 | "黄金三秒/五秒" 概念 + 开头矛盾呈现要求 |

## 3. 调研发现

### 3.1 snowflake-fiction：五类钩子系统

来源：`storyforge/process/snowflake-fiction/skills/hook-design/references/hook-types-and-criteria.md`

#### 开篇钩子（Opening Hook）通过标准

1. **前 100 字内出现异常/反常事件**
2. **前 300 字内产生至少 1 个核心疑问**
3. 信息暴露 ≤10%（"揭示 10%，隐藏 90%"）
4. 疑问驱动翻页

#### 开篇钩子失败类型

| 失败类型 | 描述 |
|----------|------|
| 世界观倾倒 (Worldview dumping) | 开头堆砌设定，读者无所适从 |
| 主角简历 (Protagonist resume) | 平铺介绍主角背景，无悬念 |
| 能力展示 (Ability exhibition) | 直接展示金手指/能力，无危机铺垫 |
| 平铺直叙 (Bland 铺陈) | 日常场景开头，无冲突无悬念 |

#### 百花钩（Multi-Type Hooks）6 种变体

1. **道具钩**：神秘物品，功能未知
2. **场景钩**：异常环境细节
3. **对话钩**：知情人隐晦信息
4. **感官钩**：反复出现的异常感官体验
5. **误会钩**：信息误差导致冲突
6. **错过钩**：关键人物/信息擦肩而过

#### 钩子密度量化标准

| 密度等级 | 活跃钩子数 | 评级 |
|----------|-----------|------|
| 密集 | ≥3 | 优秀 |
| 合格 | 1.75-3 | 良好 |
| 稀疏 | 1-1.75 | 勉强 |
| 真空 | <1 | 失败风险 |

### 3.2 snowflake-fiction：黄金三章法则

来源：`storyforge/process/snowflake-fiction/skills/quality-check/references/opening-subcheck.md`

#### 第一章（40 分）：3 秒钩子

- **核心任务**：以"爆炸性"内容开头，立即制造紧张感
- **开头公式**：环境异常 + 主角异常行为 + 致命威胁
- **两种爆款开头模板**：
  - 危机开头：主角直接身处绝境
  - 金手指降临：跳过铺垫，直接获得能力
- **检查清单**：
  - 前 300 字内有爆点
  - 主角登场
  - 高效基础信息传递
  - 避免寡淡开头
  - 避免信息轰炸
  - 避免延迟入场
  - 保持主角视角
- **一句话介绍法**：谁 + 在哪 + 发生什么 + 角色特征
- **"慢热陷阱"警告**：不要把最差的果实放在最上面

#### 第二章（30 分）：强化冲突

- **核心任务**：给主角紧迫目标 + 设置具体障碍
- **结构公式**：目标具象化 + 障碍明确化 = 读者替主角焦虑

#### 第三章（30 分）：爽点反馈

- **核心任务**：让读者尝到甜头，哪怕是小胜利
- **爽感公式**：铺垫（被看扁）→ 反转（展现实力）→ 反应（众人震惊）

### 3.3 oh-story-claudecode：实战钩子技法

来源：https://github.com/worldwonderer/oh-story-claudecode

知识库覆盖 100+ 份写作理论文件，与钩子检测直接相关的包括：

| 知识库主题 | 内容 |
|------------|------|
| 开篇模式 | 多种网文开头模板 |
| 前 500 字设计 | 具体开头策略 |
| 黄金三章开头策略 | 与 snowflake-fiction 体系一致 |
| 章首钩子 7 式 | 7 种章节开头钩子模式 |
| 章尾钩子 13 式 | 13 种章节结尾钩子模式 |
| 段落级钩子 | 段落内悬念技法 |
| 悬念编排 | 跨章节悬念管理 |

**多 Agent 协作体系**：7 个专业 Agent（故事架构师、角色设计师、叙事写手、一致性检查等），按需加载 references 中的写作理论。

### 3.4 WebNovelBench (arXiv 2025)：学术评估框架

来源：https://arxiv.org/html/2505.14818v1

- **数据基础**：4000+ 部热门中文网文（每部 >10,000 读者）
- **评估方法**：8 个叙事质量维度，LLM-as-Judge 自动评分
- **排名方法**：PCA 加权 + ECDF 百分位排名
- **验证**：茅盾文学奖作品稳定落在高端区间，确认与人类判断对齐
- **主要发现**：顶级 LLM（Qwen3-235B、DeepSeek-R1、Gemini-2.5-Pro）在叙事生成上已接近热门网文水平

**对钩子检测的启示**：学术界的自动评估侧重 LLM-as-Judge 整体打分，缺乏针对"开篇钩子"的细粒度机械检测。StoryForge3 的机械审计规则在这个维度上可以领先学术研究。

### 3.5 知乎/网文社区：黄金三秒概念

- **"黄金三秒/五秒"**：知乎和 WebNovel 平台讨论中，将"黄金三章"进一步细化为开头文字内的微级时间窗口
- **核心主张**：开头文字中的关键矛盾和钩子必须在读者最初几秒阅读内呈现
- **番茄小说/七猫小说**：平台推荐算法在前几百字内就决定推荐量
- **起点中文网作者实践**：蛊真人作者明确将"黄金三章、快速更新、冲突设置"视为黄金法则

## 4. 调研结论

### 4.1 现有规则与行业知识完全不对齐

| 行业标准 | 当前规则 | 差距 |
|----------|----------|------|
| 前 100 字内异常事件 | 只查 6 个词 | 表达力差 10 倍以上 |
| 短句冲击 | 不检测 | 完全缺失 |
| 对话/声音钩子 | 只查"声音"一词 | 不检查引号、拟声词 |
| 悬念/疑问 | 不检测 | 完全缺失 |
| 多种钩子类型识别 | 不区分 | 完全缺失 |

### 4.2 推荐重设计方向

**多维组合判定**：前三段文本，满足以下任意 2 项即 passed：

| 维度 | 检测方式 | 调研依据 |
|------|----------|----------|
| A. 短句冲击 | 前 3 段中存在 ≤10 中文字符的独立段落 | snowflake "3秒钩子" + oh-story "前500字设计" |
| B. 异常/反常事件 | 匹配异常/变化/冲击词表 | snowflake "前100字异常" + "场景钩" |
| C. 对话或声音 | 含中文引号或拟声词 | snowflake "对话钩" + "感官钩" |
| D. 悬念/疑问 | 含 `？` 或 `！` | snowflake "核心疑问" |
| E. 关键词匹配 | 保留原 6 词（降级为条件之一） | 向后兼容 |

### 4.3 为什么 ≥2 而不是 ≥1

- 单信号太容易偶然通过（一个问号不代表有效钩子）
- snowflake 钩子密度标准要求 ≥1.75 才算"合格"
- ≥2 信号组合更接近"有设计感的开头"

## 5. 附录：调研来源索引

| 来源 | 路径/URL |
|------|----------|
| snowflake-fiction 钩子类型标准 | `storyforge/process/snowflake-fiction/skills/hook-design/references/hook-types-and-criteria.md` |
| snowflake-fiction 开篇检查 | `storyforge/process/snowflake-fiction/skills/quality-check/references/opening-subcheck.md` |
| snowflake-fiction 写作避雷指南 | `storyforge/process/snowflake-fiction/skills/snowflake-fiction/references/writing-pitfalls-guide.md` |
| snowflake-fiction 钩子示例 | `storyforge/process/snowflake-fiction/skills/hook-design/references/hook-examples.md` |
| oh-story-claudecode | https://github.com/worldwonderer/oh-story-claudecode |
| WebNovelBench 论文 | https://arxiv.org/html/2505.14818v1 |
| WebNovelBench 8 维度评估 | 论文 Table 1 |
| 知乎黄金三章讨论 | https://www.zhihu.com/question/5075565579 |
| WebNovel 黄金三秒 | https://m.webnovel.com/ask/a333343718022174 |
| ProseEngine 首章分析 | https://proseengine.app/blog/how-to-write-a-first-chapter |
| InkShift 开篇钩子测试 | https://inkshift.io/resources/opening-hook |
