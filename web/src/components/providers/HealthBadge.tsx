/**
 * Provider health pill driven by `cc_probe_status`.
 * Adapted from cc-switch-main's ProviderHealthBadge, but keyed on SF3's probe
 * status (verified | request_failed | null) rather than consecutive_failures.
 */
import { Badge } from "@/components/ui/badge";

interface HealthBadgeProps {
  status?: "verified" | "request_failed" | null;
  message?: string | null;
  className?: string;
}

export function HealthBadge({ status, message, className }: HealthBadgeProps) {
  if (status === "verified") {
    return (
      <Badge variant="active" className={className} title={message ?? "已验证，可用于稿件生成"}>
        已验证
      </Badge>
    );
  }
  if (status === "request_failed") {
    return (
      <Badge variant="archived" className={className} title={message ?? undefined}>
        异常
      </Badge>
    );
  }
  return <Badge variant="muted" className={className}>未验证</Badge>;
}
