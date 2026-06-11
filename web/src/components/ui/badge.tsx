import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium", {
  variants: {
    variant: {
      default: "border-zinc-700 bg-zinc-900 text-zinc-300",
      active: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
      completed: "border-sky-400/30 bg-sky-400/10 text-sky-300",
      archived: "border-orange-400/30 bg-orange-400/10 text-orange-300",
      muted: "border-zinc-700 bg-zinc-900/60 text-zinc-500"
    }
  },
  defaultVariants: {
    variant: "default"
  }
});

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant, className }))} {...props} />;
}

export { Badge, badgeVariants };
