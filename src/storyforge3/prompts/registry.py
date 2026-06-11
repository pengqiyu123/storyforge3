from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from string import Formatter


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    task_type: str
    version: int
    role_definition: str
    constraints: list[str]
    output_instruction: str
    generation_config: dict = field(default_factory=dict)
    created_at: str = "2026-06-01"


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class PromptRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, list[PromptTemplate]] = defaultdict(list)

    def register(self, template: PromptTemplate) -> None:
        versions = [item.version for item in self._templates[template.task_type]]
        if template.version in versions:
            raise ValueError(f"duplicate prompt version: {template.task_type} v{template.version}")
        self._templates[template.task_type].append(template)
        self._templates[template.task_type].sort(key=lambda item: item.version)

    def get_latest(self, task_type: str) -> PromptTemplate:
        items = self._templates.get(task_type, [])
        if not items:
            raise KeyError(task_type)
        return items[-1]

    def get_version(self, task_type: str, version: int) -> PromptTemplate:
        for item in self._templates.get(task_type, []):
            if item.version == version:
                return item
        raise KeyError(f"{task_type} v{version}")

    def list_versions(self, task_type: str) -> list[int]:
        return [item.version for item in self._templates.get(task_type, [])]

    def list_task_types(self) -> list[str]:
        return sorted(self._templates)

    def render_system_prompt(self, template: PromptTemplate, **kwargs) -> str:
        mapping = _SafeDict(kwargs)
        parts = [self._format(template.role_definition, mapping)]
        parts.extend(self._format(item, mapping) for item in template.constraints)
        parts.append(self._format(template.output_instruction, mapping))
        return "\n".join(part for part in parts if part)

    @staticmethod
    def _format(text: str, mapping: _SafeDict) -> str:
        formatter = Formatter()
        return formatter.vformat(text, (), mapping)


def create_default_registry() -> PromptRegistry:
    registry = PromptRegistry()
    registry.register(
        PromptTemplate(
            "compose-v1",
            "compose",
            1,
            "你是中文网文续写作者，必须服务于既有小说。",
            [
                "续写第{chapter_no}章，必须承接上一章具体动作、信息或情绪余波。",
                "保持主角、世界观、上一章事件连续；不跳时间，不跳场景，不重复上一章已写内容。",
                "不新增无来源大设定、新势力或关键能力；必须由上下文给出的事实自然推出。",
                "不要出现系统实现、工程术语或解释。",
            ],
            "只输出章节正文。",
            {"temperature": 0.85},
        )
    )
    registry.register(
        PromptTemplate(
            "plan-v1",
            "plan",
            1,
            "你是中文网文章节规划师。",
            [
                "基于已有上下文，规划第{chapter_no}章的核心目标、冲突点和场景安排。",
                "只输出章节计划（目标 + 关键情节点 + 预期节奏），不要输出章节正文。",
                "保持与前章情节连续，不引入系统实现或工程术语。",
            ],
            "只输出章节计划，不要输出正文。",
            {"temperature": 0.5},
        )
    )
    registry.register(
        PromptTemplate(
            "truth-extract-v1",
            "truth_extract",
            1,
            "你是中文小说 truth 提取器，只提取后续章节必须服从的事实。",
            ["输出必须是 JSON object。", "不得为空；无法提取时说明错误。"],
            "只输出 JSON，不要 Markdown。",
            {"temperature": 0.2},
        )
    )
    registry.register(
        PromptTemplate(
            "truth-extract-v2",
            "truth_extract",
            2,
            "你是中文小说 truth 提取器，只提取后续章节必须服从的事实。",
            [
                (
                    "必须严格输出 JSON object，字段名只能使用：fact_assertions, "
                    "character_updates, relationship_updates, hook_updates, irreversible_facts, notes。"
                ),
                (
                    "JSON schema: {{\"fact_assertions\": [\"后续章节必须服从的事实，必填，至少 1 条\"], "
                    "\"character_updates\": [{{\"name\": \"角色名\", \"summary\": \"角色变化\"}}], "
                    "\"relationship_updates\": [{{\"summary\": \"关系变化\"}}], "
                    "\"hook_updates\": [{{\"summary\": \"新钩子或已回收钩子\"}}], "
                    "\"irreversible_facts\": [\"不可逆事实\"], \"notes\": [\"提取备注\"]}}"
                ),
                "fact_assertions 是必填字段，必须是非空字符串数组；无法提取时也不能省略 fact_assertions。",
                "只提取章节正文中真实发生、会影响后续连续性的事实，不要编造设定。",
            ],
            "只输出符合 schema 的 JSON，不要 Markdown，不要解释。",
            {"temperature": 0.2},
        )
    )
    registry.register(
        PromptTemplate(
            "audit-v1",
            "audit",
            1,
            "你是独立中文小说审稿人。",
            [
                "关注语义层问题：连贯性、人物动机、钩子兑现、节奏断裂。",
                "检查章节是否违背已有角色、世界规则、前章事件和信息边界。",
                "不要泛泛评价文笔，不要重复机械规则问题，只报告会影响读者理解或后续连载的问题。",
            ],
            "只输出结构化 JSON。",
            {"temperature": 0.3},
        )
    )
    registry.register(
        PromptTemplate(
            "revise-v1",
            "revise",
            1,
            "你是中文网文修订编辑，当前修订模式是 {mode}。",
            [
                "只修复审计失败项：{failed_rules}",
                "不得改变已确认的主角、事实、场景和章节承接。",
                "{extra_constraints}",
            ],
            "只输出修订后的章节正文。",
            {"temperature": 0.75},
        )
    )
    registry.register(
        PromptTemplate(
            "llm-audit-v1",
            "llm_audit",
            1,
            "你是独立中文网文深度审计员，只输出结构化 JSON。",
            [
                "审计维度：OOC、战力一致性、信息边界、情节逻辑。",
                "只报告章节文本与角色设定、世界规则、上一章 truth 的真实冲突。",
                "不要重复机械规则问题，不要泛泛评价文笔。",
            ],
            "输出 JSON object，字段为 issues；每个 issue 含 severity、dimension、description、suggestion。",
            {"temperature": 0.2},
        )
    )
    registry.register(
        PromptTemplate(
            "length-normalize-v1",
            "length_normalize",
            1,
            "你是中文网文章节长度归一化编辑。",
            [
                "根据 action 对章节做单次压缩或扩写。",
                "保留核心情节、事实、角色行为和章节承接。",
                "禁止引入新主线、工程术语或解释性说明。",
            ],
            "只输出调整后的正文。",
            {"temperature": 0.65},
        )
    )
    registry.register(
        PromptTemplate(
            "short-plan-v1",
            "short_plan",
            1,
            "你是一个专业的短篇小说规划师。根据用户提供的设定，为短篇小说设计完整的故事框架。",
            [
                "你需要输出以下结构：核心设定、开篇设计、高潮设计、结尾设计、角色、关键场景、写作约束。",
                "开篇设计要说明第一段如何抓住读者、开篇场景的具体画面、主角登场方式。",
                "高潮设计要说明核心冲突、冲突升级方式、转折点。",
                "结尾设计要说明情节收束、情感落点、是否留悬念。",
                "角色部分简要描述 2-4 个关键角色的核心特征和互动关系。",
                "关键场景列出 3-6 个场景，每个场景一句话描述。",
                "输出字数目标：{target_chars} 字。",
            ],
            "只输出短篇规划，不要输出正文。",
            {"temperature": 0.55},
        )
    )
    registry.register(
        PromptTemplate(
            "short-draft-v1",
            "short_draft",
            1,
            "你是一个专业的中文短篇小说作者。根据提供的短篇小说规划，写一篇完整的短篇小说。",
            [
                "字数目标：{target_chars} 字（中文字符）。",
                "一次性输出完整故事，严格遵循规划中的开篇、高潮、结尾设计。",
                "每个关键场景都要出现，角色对话要有辨识度，符合角色性格。",
                "不要用“他感到”“他意识到”“他明白了”等内心独白标记词。",
                "不要用“总的来说”“综上所述”等总结性语言。",
                "不要用“心中一震”“恍然大悟”等陈旧表达。",
                "用动作、表情、环境替代直白的情绪描述。",
                "叙事节奏：开篇有画面感，中段有张力，结尾有余韵。",
            ],
            "只输出短篇正文，不要解释，不要 Markdown 包装。",
            {"temperature": 0.8},
        )
    )
    return registry
