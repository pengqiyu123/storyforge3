from __future__ import annotations

from dataclasses import dataclass


OPEN_STATUSES = {"open", "advanced"}
RESOLVED_STATUSES = {"resolved", "invalidated"}


@dataclass(frozen=True)
class OverdueHook:
    hook_id: str
    label: str
    introduced_in: int
    chapters_overdue: int
    level: str


@dataclass(frozen=True)
class HookDensityReport:
    new_hooks: int
    resolved_hooks: int
    net_pressure: int
    density_score: float
    overdue_list: tuple[OverdueHook, ...]
    warning_level: str


class HookDensityAnalyzer:
    def analyze(
        self,
        chapter_text: str,
        hook_ledger: list[dict] | dict,
        *,
        chapter_no: int,
        overdue_warning_threshold: int = 10,
        overdue_critical_threshold: int = 20,
    ) -> HookDensityReport:
        hooks = self._normalize_hooks(hook_ledger)
        new_hooks = sum(1 for hook in hooks if self._as_int(hook.get("introduced_in")) == chapter_no)
        resolved_hooks = sum(1 for hook in hooks if self._as_int(hook.get("resolved_in")) == chapter_no)
        open_after = sum(1 for hook in hooks if self._is_open_after(hook, chapter_no))
        overdue = self._overdue_hooks(
            hooks,
            chapter_no=chapter_no,
            warning_threshold=overdue_warning_threshold,
            critical_threshold=overdue_critical_threshold,
        )
        net_pressure = new_hooks - resolved_hooks
        density_score = round((new_hooks + resolved_hooks * 0.5) / max(1, open_after), 4)
        return HookDensityReport(
            new_hooks=new_hooks,
            resolved_hooks=resolved_hooks,
            net_pressure=net_pressure,
            density_score=density_score,
            overdue_list=tuple(overdue),
            warning_level=self._warning_level(overdue),
        )

    @staticmethod
    def _normalize_hooks(hook_ledger: list[dict] | dict) -> list[dict]:
        hooks = hook_ledger.get("hooks", []) if isinstance(hook_ledger, dict) else hook_ledger
        return [hook for hook in hooks if isinstance(hook, dict) and "hook_id" in hook]

    @staticmethod
    def _status(hook: dict) -> str:
        return str(hook.get("status") or "open").strip().lower()

    @staticmethod
    def _as_int(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _is_open_at_start(self, hook: dict, chapter_no: int) -> bool:
        introduced_in = self._as_int(hook.get("introduced_in"))
        resolved_in = self._as_int(hook.get("resolved_in"))
        return introduced_in < chapter_no and (resolved_in == 0 or resolved_in >= chapter_no)

    def _is_open_after(self, hook: dict, chapter_no: int) -> bool:
        introduced_in = self._as_int(hook.get("introduced_in"))
        resolved_in = self._as_int(hook.get("resolved_in"))
        return introduced_in <= chapter_no and (resolved_in == 0 or resolved_in > chapter_no)

    def _overdue_hooks(
        self,
        hooks: list[dict],
        *,
        chapter_no: int,
        warning_threshold: int,
        critical_threshold: int,
    ) -> list[OverdueHook]:
        overdue: list[OverdueHook] = []
        for hook in hooks:
            if self._status(hook) not in OPEN_STATUSES:
                continue
            introduced_in = self._as_int(hook.get("introduced_in"))
            age = chapter_no - introduced_in
            if age <= warning_threshold:
                continue
            level = "critical" if age > critical_threshold else "warning"
            overdue.append(
                OverdueHook(
                    hook_id=str(hook.get("hook_id", "")),
                    label=str(hook.get("label", "")),
                    introduced_in=introduced_in,
                    chapters_overdue=age - warning_threshold,
                    level=level,
                )
            )
        return overdue

    @staticmethod
    def _warning_level(overdue: list[OverdueHook]) -> str:
        if any(item.level == "critical" for item in overdue):
            return "critical"
        if overdue:
            return "watch"
        return "healthy"
