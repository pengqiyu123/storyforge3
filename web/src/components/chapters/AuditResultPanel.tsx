import { AlertTriangle, CheckCircle2, MapPin, ShieldAlert, XCircle } from "lucide-react";
import type { AuditResult, RuleResult } from "@/api/chapters";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface AuditResultPanelProps {
  result?: AuditResult | null;
  onLocateIssue?: (rule: RuleResult) => void;
}

export function AuditResultPanel({ result, onLocateIssue }: AuditResultPanelProps) {
  if (!result) {
    return null;
  }

  const rules = result.rule_results ?? [];
  const passed = rules.filter((rule) => rule.passed).length;
  const warnings = rules.filter((rule) => !rule.passed && rule.severity === "WARNING").length;
  const blocking = rules.filter((rule) => !rule.passed && rule.severity === "BLOCKING").length;

  return (
    <Card className={cn("border-zinc-800/80 bg-black/25", result.passed ? "border-emerald-400/20" : "border-red-400/25")}>
      <CardHeader className="pb-3">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <CardTitle className="flex items-center gap-2 text-base">
            {result.passed ? <CheckCircle2 className="h-4 w-4 text-emerald-300" /> : <ShieldAlert className="h-4 w-4 text-red-300" />}
            {result.passed ? "审计通过" : "审计未通过"}
          </CardTitle>
          <Badge variant={result.passed ? "active" : "archived"}>
            {passed} passed / {warnings} warnings / {blocking} blocking
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {rules.length ? (
          rules.map((rule) => <RuleRow key={rule.rule_id} rule={rule} onLocateIssue={onLocateIssue} />)
        ) : (
          <p className="text-sm text-zinc-500">暂无规则结果。</p>
        )}
      </CardContent>
    </Card>
  );
}

function RuleRow({ rule, onLocateIssue }: { rule: RuleResult; onLocateIssue?: (rule: RuleResult) => void }) {
  const Icon = rule.passed ? CheckCircle2 : rule.severity === "BLOCKING" ? XCircle : AlertTriangle;
  const snippet = typeof rule.detail?.snippet === "string" ? rule.detail.snippet : "";
  const canLocate = !rule.passed && hasParagraphLocations(rule) && Boolean(onLocateIssue);
  const content = (
    <>
      <div className="flex min-w-0 items-start gap-2">
        <Icon className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0">
          <p className="font-medium text-zinc-200">{rule.rule_id}</p>
          {!rule.passed ? <p className="mt-1 text-xs leading-5 opacity-90">{rule.message}</p> : null}
          {snippet ? <p className="mt-2 line-clamp-2 text-xs leading-5 text-zinc-500">{snippet}</p> : null}
        </div>
      </div>
      <span className="flex items-center justify-end gap-2 text-xs uppercase tracking-wide text-zinc-500">
        {canLocate ? <MapPin className="h-3.5 w-3.5 text-amber-200" /> : null}
        {rule.severity}
      </span>
    </>
  );
  const className = cn(
    "grid w-full gap-2 rounded-md border border-zinc-900 bg-zinc-950/60 p-3 text-left text-sm sm:grid-cols-[1fr_auto]",
    rule.passed && "text-zinc-500",
    !rule.passed && rule.severity === "WARNING" && "border-amber-300/20 text-amber-200",
    !rule.passed && rule.severity === "BLOCKING" && "border-red-400/20 text-red-300",
    canLocate && "cursor-pointer hover:border-amber-200/50 hover:bg-zinc-900/80"
  );

  if (canLocate) {
    return (
      <button type="button" aria-label={`定位 ${rule.rule_id}`} className={className} onClick={() => onLocateIssue?.(rule)}>
        {content}
      </button>
    );
  }

  return (
    <div className={className}>
      {content}
    </div>
  );
}

function hasParagraphLocations(rule: RuleResult) {
  return Array.isArray(rule.detail?.paragraph_indices) && rule.detail.paragraph_indices.length > 0;
}
