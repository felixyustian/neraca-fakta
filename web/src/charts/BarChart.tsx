import { useMemo, useState } from "react";
import { niceTicks } from "../format";
import { useWidth } from "../hooks";
import { TipRow, Tooltip } from "./Tooltip";

export interface BarSeries {
  label: string;
  color: string; // CSS var, e.g. "var(--series-1)"
}

export interface BarRow {
  category: string;
  values: (number | null)[]; // one per series
  extra?: string; // shown under the values in the tooltip
}

interface Props {
  series: BarSeries[];
  rows: BarRow[];
  format: (v: number) => string;
  tick: (v: number) => string;
  labelLast?: boolean; // direct-label the latest bar(s)
  ariaLabel: string;
}

const H = 240;
const M = { top: 22, right: 8, bottom: 28, left: 56 };
const BAR_MAX = 24;
const GAP = 2;
const R = 4;

/** Rect with a 4px radius on the data end only (top for positive, bottom for negative). */
function barPath(x: number, w: number, yBase: number, yVal: number): string {
  const h = Math.abs(yBase - yVal);
  const r = Math.min(R, h, w / 2);
  if (yVal <= yBase) {
    return `M${x},${yBase}V${yVal + r}Q${x},${yVal} ${x + r},${yVal}H${x + w - r}Q${x + w},${yVal} ${x + w},${yVal + r}V${yBase}Z`;
  }
  return `M${x},${yBase}V${yVal - r}Q${x},${yVal} ${x + r},${yVal}H${x + w - r}Q${x + w},${yVal} ${x + w},${yVal - r}V${yBase}Z`;
}

/** Grouped columns from one zero baseline; negative values hang below it. */
export default function BarChart({ series, rows, format, tick, labelLast = true, ariaLabel }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{ row: number; s: number } | null>(null);

  const g = useMemo(() => {
    const all = rows.flatMap((r) => r.values).filter((v): v is number => v !== null);
    const ticks = niceTicks(Math.min(0, ...all), Math.max(0, ...all), 4);
    const y0 = ticks[0];
    const y1 = ticks[ticks.length - 1];
    const iw = width - M.left - M.right;
    const ih = H - M.top - M.bottom;
    const band = iw / Math.max(1, rows.length);
    const bw = Math.min(BAR_MAX, (band * 0.7 - GAP * (series.length - 1)) / series.length);
    const groupW = bw * series.length + GAP * (series.length - 1);
    const y = (v: number) => M.top + ih - ((v - y0) / (y1 - y0 || 1)) * ih;
    const x = (row: number, s: number) => M.left + band * row + (band - groupW) / 2 + s * (bw + GAP);
    return { ticks, y, x, bw, band };
  }, [rows, series.length, width]);

  const base = g.y(0);
  return (
    <div className="viz" ref={ref}>
      {series.length > 1 && (
        <ul className="legend-row">
          {series.map((s) => (
            <li key={s.label}>
              <span className="swatch" style={{ background: s.color }} aria-hidden />
              {s.label}
            </li>
          ))}
        </ul>
      )}
      <svg width={width} height={H} role="img" aria-label={ariaLabel}>
        {g.ticks.map((v) => (
          <g key={v}>
            <line className={v === 0 ? "baseline" : "grid"} x1={M.left} x2={width - M.right} y1={g.y(v)} y2={g.y(v)} />
            <text className="tick" x={M.left - 8} y={g.y(v)} dy="0.32em" textAnchor="end">
              {tick(v)}
            </text>
          </g>
        ))}
        {rows.map((r, ri) => (
          <g key={r.category}>
            <text className="tick" x={M.left + g.band * ri + g.band / 2} y={H - 8} textAnchor="middle">
              {r.category}
            </text>
            {r.values.map((v, si) =>
              v === null ? null : (
                <path
                  key={si}
                  d={barPath(g.x(ri, si), g.bw, base, g.y(v))}
                  fill={series[si].color}
                  className={`bar ${hover && (hover.row !== ri || hover.s !== si) ? "dim" : ""}`}
                />
              ),
            )}
            {labelLast && ri === rows.length - 1 &&
              r.values.map((v, si) =>
                v === null ? null : (
                  <text
                    key={`l${si}`}
                    className="point-label"
                    x={g.x(ri, si) + g.bw / 2}
                    y={v >= 0 ? g.y(v) - 6 : g.y(v) + 14}
                    textAnchor="middle"
                  >
                    {tick(v)}
                  </text>
                ),
              )}
            {/* Hit target: the whole band slice per bar, bigger than the painted mark. */}
            {r.values.map((_, si) => (
              <rect
                key={`h${si}`}
                x={g.x(ri, si) - GAP}
                y={M.top}
                width={g.bw + GAP * 2}
                height={H - M.top - M.bottom}
                fill="transparent"
                tabIndex={0}
                aria-label={`${r.category} ${series[si].label}: ${r.values[si] === null ? "—" : format(r.values[si]!)}`}
                onPointerEnter={() => setHover({ row: ri, s: si })}
                onPointerLeave={() => setHover(null)}
                onFocus={() => setHover({ row: ri, s: si })}
                onBlur={() => setHover(null)}
              />
            ))}
          </g>
        ))}
      </svg>
      {hover && rows[hover.row].values[hover.s] !== null && (
        <Tooltip x={g.x(hover.row, hover.s) + g.bw / 2} y={g.y(Math.max(0, rows[hover.row].values[hover.s]!))} width={width}>
          <div className="tip-title">{rows[hover.row].category}</div>
          {series.map((s, si) =>
            rows[hover.row].values[si] === null ? null : (
              <TipRow key={s.label} color={s.color} value={format(rows[hover.row].values[si]!)} label={s.label} />
            ),
          )}
          {rows[hover.row].extra && <div className="tip-extra">{rows[hover.row].extra}</div>}
        </Tooltip>
      )}
    </div>
  );
}
