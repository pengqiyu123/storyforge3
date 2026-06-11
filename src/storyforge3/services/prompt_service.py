from __future__ import annotations

from storyforge3.prompts.registry import PromptRegistry, PromptTemplate, create_default_registry


class PromptService:
    """版本化 Prompt 模板管理服务。"""

    def __init__(self, registry: PromptRegistry | None = None) -> None:
        self._registry = registry or create_default_registry()

    def get(self, task_type: str, version: int | None = None) -> PromptTemplate:
        """获取指定任务类型的模板；version 为空时取最新。"""
        if version is None:
            return self._registry.get_latest(task_type)
        return self._registry.get_version(task_type, version)

    def render(self, task_type: str, **kwargs: object) -> str:
        """渲染指定任务类型的最新版系统提示词。"""
        template = self._registry.get_latest(task_type)
        return self._registry.render_system_prompt(template, **kwargs)

    def list_templates(self) -> list[dict]:
        """列出所有任务类型及版本号。"""
        return [
            {"task_type": task_type, "versions": self._registry.list_versions(task_type)}
            for task_type in self._registry.list_task_types()
        ]
