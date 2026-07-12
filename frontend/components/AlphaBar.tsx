/**
 * AlphaBar — signature element. Cross-sectional z drawn as a deviation
 * bar centered at zero; clipped at ±3σ with a notch (winsorization
 * convention) so one outlier can't flatten the page.
 */
import { cn } from "@/lib/utils";

export default function AlphaBar({
  value,
  max = 3,
  width = "w-24",
}: {
  value: number | null;
  max?: number;
  width?: string;
}) {
  if (value === null || Number.isNaN(value)) {
    return <span className="font-mono text-2xs text-muted">n/a</span>;
  }
  const clipped = Math.max(-max, Math.min(max, value));
  const pct = (Math.abs(clipped) / max) * 50;
  const positive = clipped >= 0;
  const wasClipped = Math.abs(value) > max;

  return (
    <div className="flex items-center gap-2">
      <div className={cn("relative h-2 shrink-0 rounded-[2px] bg-panel2", width)}>
        <div className="absolute left-1/2 top-0 h-full w-px bg-rule" />
        <div
          className={cn("absolute top-0 h-full", positive ? "bg-gain" : "bg-loss")}
          style={
            positive
              ? { left: "50%", width: `${pct}%` }
              : { right: "50%", width: `${pct}%` }
          }
        />
        {wasClipped && (
          <div
            className={cn(
              "absolute top-[-2px] h-[12px] w-[2px]",
              positive ? "right-0 bg-gain" : "left-0 bg-loss",
            )}
          />
        )}
      </div>
      <span
        className={cn(
          "font-mono text-2xs tabular-nums",
          positive ? "text-gain" : "text-loss",
        )}
      >
        {value >= 0 ? "+" : ""}
        {value.toFixed(2)}
      </span>
    </div>
  );
}
