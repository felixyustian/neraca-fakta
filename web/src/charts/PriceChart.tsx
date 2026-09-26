import { useMemo, useState } from "react";
import { date, niceTicks, price } from "../format";
import { useWidth } from "../hooks";
import { useI18n } from "../i18n";
import { TipRow, Tooltip } from "./Tooltip";

interface Props {
  points: { date: string; close: number }[];
}

const H = 220;
const M = { top: 16, right: 64, bottom: 28, left: 8 };

/** 90-day close: 2px line over a 10% wash, crosshair tooltip, labelled end, min and max. */
export default function PriceChart({ points }: Props) {
  const { lang, t } = useI18n();
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const g = useMemo(() => {
    const closes = points.map((p) => p.close);
    const lo = Math.min(...closes);
    const hi = Math.max(...closes);
    // A flat series (e.g. a stock pinned at its floor price) still gets a readable, whole-number axis.
    const pad = hi > lo ? (hi - lo) * 0.15 : Math.max(1, hi * 0.04);
    const ticks = niceTicks(lo - pad, hi + pad, 4);
    const y0 = ticks[0];
    const y1 = ticks[ticks.length - 1];
    const iw = width - M.left - M.right;
    const ih = H - M.top - M.bottom;
    const x = (i: number) => M.left + (points.length === 1 ? iw / 2 : (i / (points.length - 1)) * iw);
    const y = (v: number) => M.top + ih - ((v - y0) / (y1 - y0 || 1)) * ih;
    const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.close).toFixed(1)}`).join("");
    const area = `${line}L${x(points.length - 1)},${M.top + ih}L${x(0)},${M.top + ih}Z`;
    const iMin = closes.indexOf(lo);
    const iMax = closes.indexOf(hi);
    // Month boundaries for x ticks.
    const months = points
      .map((p, i) => ({ i, m: p.date.slice(0, 7) }))
      .filter((d, k, arr) => k === 0 || d.m !== arr[k - 1].m)
      .slice(1);
    return { ticks, x, y, line, area, iMin, iMax, months, ih, flat: hi === lo };
  }, [points, width]);

  if (points.length < 2) return <p className="muted">{t("noPrices")}</p>;

  const last = points.length - 1;
  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const rel = (e.clientX - rect.left) / rect.width;
    setHover(Math.max(0, Math.min(last, Math.round(rel * last))));
  };

  return (
    <div className="viz" ref={ref}>
      <svg width={width} height={H} role="img" aria-label={t("priceChartTitle", { from: date(points[0].date, lang), to: date(points[last].date, lang) })}>
        {g.ticks.map((v) => (
          <g key={v}>
            <line className="grid" x1={M.left} x2={width - M.right} y1={g.y(v)} y2={g.y(v)} />
            <text className="tick" x={width - M.right + 8} y={g.y(v)} dy="0.32em">
              {v.toLocaleString(lang === "id" ? "id-ID" : "en-US")}
            </text>
          </g>
        ))}
        {g.months.map(({ i, m }) => (
          <text key={m} className="tick" x={g.x(i)} y={H - 8} textAnchor="middle">
            {new Date(m + "-01T00:00:00").toLocaleDateString(lang === "id" ? "id-ID" : "en-US", { month: "short" })}
          </text>
        ))}
        <path d={g.area} className="area s1" />
        <path d={g.line} className="line s1" />
        {/* Selective labels: the low and the high (skipped when the series is flat), and the last close. */}
        {g.flat ? null : [g.iMin, g.iMax].filter((i, k, a) => a.indexOf(i) === k && i !== last).map((i) => (
          <text
            key={i}
            className="point-label"
            x={g.x(i)}
            y={g.y(points[i].close) + (i === g.iMin ? 16 : -8)}
            textAnchor={g.x(i) < M.left + 40 ? "start" : g.x(i) > width - M.right - 40 ? "end" : "middle"}
          >
            {price(points[i].close, lang)}
          </text>
        ))}
        <text className="point-label" x={g.x(last) - 8} y={g.y(points[last].close) - 10} textAnchor="end">
          {price(points[last].close, lang)}
        </text>
        <circle className="end-dot s1" cx={g.x(last)} cy={g.y(points[last].close)} r={4.5} />
        {hover !== null && (
          <g className="crosshair">
            <line x1={g.x(hover)} x2={g.x(hover)} y1={M.top} y2={M.top + g.ih} />
            <circle className="end-dot s1" cx={g.x(hover)} cy={g.y(points[hover].close)} r={4.5} />
          </g>
        )}
        <rect
          x={M.left}
          y={0}
          width={width - M.left - M.right}
          height={H}
          fill="transparent"
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        />
      </svg>
      {hover !== null && (
        <Tooltip x={g.x(hover)} y={g.y(points[hover].close)} width={width}>
          <TipRow color="var(--series-1)" line value={price(points[hover].close, lang)} label={date(points[hover].date, lang)} />
        </Tooltip>
      )}
    </div>
  );
}
