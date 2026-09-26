import type { ReactNode } from "react";

/** One tooltip for a chart; positioned in the chart's own box, flips near the right edge. */
export function Tooltip({ x, y, width, children }: { x: number; y: number; width: number; children: ReactNode }) {
  const flip = x > width - 170;
  return (
    <div
      className="viz-tooltip"
      role="status"
      style={{ left: flip ? undefined : x + 12, right: flip ? width - x + 12 : undefined, top: Math.max(0, y - 10) }}
    >
      {children}
    </div>
  );
}

export function TipRow({ color, label, value, line = false }: { color?: string; label: string; value: string; line?: boolean }) {
  return (
    <div className="tip-row">
      {color && <span className={line ? "tip-key line" : "tip-key"} style={{ background: color }} aria-hidden />}
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
