import { useState } from "react";
import { useWidth } from "../hooks";
import type { SeriesPoint } from "../types";

interface Props {
  points: SeriesPoint[];
  height?: number;
  format: (v: number) => string;
  formatDate: (d: string) => string;
  label: string;
}

/** Compact trend line: 2px line over a 10% wash, end dot, hover readout. Single series, no legend. */
export default function Sparkline({ points, height = 56, format, formatDate, label }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>(240);
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return null;
  const vals = points.map((p) => p.value);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = 5;
  const x = (i: number) => pad + (i / (points.length - 1)) * (width - pad * 2);
  const y = (v: number) => pad + (1 - (v - lo) / (hi - lo || 1)) * (height - pad * 2);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
  const last = points.length - 1;
  const up = vals[last] >= vals[0];
  const i = hover ?? last;

  return (
    <div className="spark" ref={ref}>
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`${label}: ${format(vals[0])} → ${format(vals[last])}`}
        onPointerMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          setHover(Math.max(0, Math.min(last, Math.round(((e.clientX - r.left - pad) / (r.width - pad * 2)) * last))));
        }}
        onPointerLeave={() => setHover(null)}
      >
        <path d={`${line}L${x(last)},${height}L${x(0)},${height}Z`} className={`spark-area ${up ? "up" : "down"}`} />
        <path d={line} className={`spark-line ${up ? "up" : "down"}`} />
        {hover !== null && <line className="spark-cross" x1={x(i)} x2={x(i)} y1={0} y2={height} />}
        <circle className={`spark-dot ${up ? "up" : "down"}`} cx={x(i)} cy={y(vals[i])} r={3.5} />
      </svg>
      <div className="spark-read small">
        <span>{formatDate(points[i].date)}</span>
        <strong>{format(vals[i])}</strong>
      </div>
    </div>
  );
}
