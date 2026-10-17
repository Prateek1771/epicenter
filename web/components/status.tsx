import { CircleCheck, CircleDashed, CircleDot, CircleHelp, CircleSlash, CircleX, Loader2, Send, ShieldCheck } from "@/components/icons";

import { STATUS_LABEL } from "@/lib/format";
import { cn } from "@/lib/utils";

const STYLE: Record<string, { cls: string; Icon: typeof CircleDot }> = {
  open: { cls: "text-st-open bg-st-open/10 ring-st-open/25", Icon: CircleDashed },
  supported: { cls: "text-st-supported bg-st-supported/10 ring-st-supported/25", Icon: CircleDot },
  refuted: { cls: "text-st-refuted bg-st-refuted/10 ring-st-refuted/25", Icon: CircleX },
  inconclusive: { cls: "text-st-inconclusive bg-st-inconclusive/10 ring-st-inconclusive/25", Icon: CircleHelp },
  pruned: { cls: "text-st-pruned bg-st-pruned/10 ring-st-pruned/20", Icon: CircleSlash },
  confirmed: { cls: "text-st-confirmed bg-st-confirmed/12 ring-st-confirmed/35", Icon: CircleCheck },
  diagnosing: { cls: "text-signal bg-signal/12 ring-signal/30", Icon: Loader2 },
  diagnosed: { cls: "text-st-confirmed bg-st-confirmed/12 ring-st-confirmed/30", Icon: CircleCheck },
  no_root_cause: { cls: "text-ov-missed bg-ov-missed/10 ring-ov-missed/30", Icon: CircleHelp },
  delivered: { cls: "text-st-supported bg-st-supported/10 ring-st-supported/30", Icon: Send },
  resolved: { cls: "text-muted-foreground bg-muted ring-border", Icon: ShieldCheck },
};

/** Status as colour + icon + word: never colour alone (accessibility). */
export function StatusPill({ status, className }: { status: string; className?: string }) {
  const s = STYLE[status] ?? STYLE.open;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full bg-white/5 px-2 py-0.5 text-xs font-normal text-mist whitespace-nowrap",
        className,
      )}
    >
      <s.Icon className={cn("size-3.5", s.cls.split(" ")[0], status === "diagnosing" && "animate-spin")} aria-hidden />
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

/** A thin horizontal bar for a 0..1 value. */
export function Meter({ value, className, label }: { value: number; className?: string; label?: string }) {
  const v = Math.max(0, Math.min(1, value));
  return (
    <div
      className="h-1 w-full overflow-hidden rounded-full bg-graphite"
      role="meter"
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={Number(v.toFixed(3))}
      aria-label={label}
    >
      <div className={cn("h-full rounded-full bg-signal transition-[width] duration-500", className)} style={{ width: `${v * 100}%` }} />
    </div>
  );
}
