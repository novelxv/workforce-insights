"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { fmtTick, fmtValue } from "@/lib/format";
import type { Unit } from "@/lib/types";

/**
 * Hand-built SVG charts. One series each, so the panel title names the series and no
 * legend is needed. 2px lines, >=8px markers, recessive grid, text in text colours
 * (never the series colour), and a hover layer with hit targets wider than the marks.
 */

export interface TrendPoint {
  key: string;
  label: string;
  value: number | null;
  detail?: ReactNode;
}

function useWidth(fallback = 640) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.round(entry.contentRect.width))));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

function niceStep(raw: number): number {
  const pow = 10 ** Math.floor(Math.log10(raw));
  for (const m of [1, 2, 2.5, 5, 10]) if (raw <= m * pow) return m * pow;
  return 10 * pow;
}

function domain(values: number[], fromZero: boolean, unitMax?: number) {
  const hi = Math.max(...values);
  const lo = fromZero ? 0 : Math.min(...values);
  const span = hi - lo || Math.abs(hi) || 1;
  const step = niceStep(span / 4);
  // Never pad below zero when nothing is negative: a rate cannot be -25%.
  const padded = Math.floor((lo - step / 3) / step) * step;
  const bottom = fromZero ? 0 : lo >= 0 ? Math.max(0, padded) : padded;
  let top = Math.ceil((hi + step / 3) / step) * step;
  if (unitMax !== undefined) top = Math.min(top, unitMax);
  const ticks: number[] = [];
  for (let v = bottom; v <= top + step / 1000; v += step) ticks.push(Number(v.toFixed(10)));
  return { min: bottom, max: top, ticks };
}

export function TrendLine({
  points,
  unit,
  height = 220,
  xs,
  fromZero = false,
  ariaLabel,
}: {
  points: TrendPoint[];
  unit: Unit;
  height?: number;
  /** Numeric x positions (e.g. months since hire); evenly spaced when omitted. */
  xs?: number[];
  fromZero?: boolean;
  ariaLabel: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  // Drawn at the container's real width so axis text stays 11px in a half-width panel.
  const [ref, width] = useWidth();
  const pad = { top: 14, right: 18, bottom: 28, left: 52 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const present = points.filter((p) => p.value !== null).map((p) => p.value as number);

  const { min, max, ticks } = domain(
    present.length ? present : [0, 1],
    fromZero,
    unit === "percent" && fromZero ? 1 : undefined,
  );
  if (points.length === 0) return null;

  const xMin = xs ? Math.min(...xs) : 0;
  const xMax = xs ? Math.max(...xs) : points.length - 1;
  const x = (i: number) => {
    const raw = xs ? xs[i] : i;
    return pad.left + (xMax === xMin ? innerW / 2 : ((raw - xMin) / (xMax - xMin)) * innerW);
  };
  const y = (v: number) => pad.top + innerH - ((v - min) / (max - min || 1)) * innerH;

  // Break the line where a value is withheld or not yet observable.
  const segments: string[] = [];
  let current = "";
  points.forEach((p, i) => {
    if (p.value === null) {
      if (current) segments.push(current);
      current = "";
      return;
    }
    current += `${current ? "L" : "M"}${x(i)},${y(p.value)}`;
  });
  if (current) segments.push(current);

  const active = hover !== null ? points[hover] : null;
  const every = Math.ceil(points.length / Math.max(2, Math.floor(innerW / 70)));

  return (
    <div className="relative" ref={ref}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={ariaLabel}
        onMouseLeave={() => setHover(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
            <text x={pad.left - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--text-3)">
              {fmtTick(t, unit)}
            </text>
          </g>
        ))}
        {points.map((p, i) => {
          if (i % every !== 0 && i !== points.length - 1 && hover !== i) return null;
          if (hover !== null && hover !== i && Math.abs(hover - i) < every / 2 + 0.5) return null;
          return (
            <text
              key={p.key}
              x={x(i)}
              y={height - 8}
              textAnchor="middle"
              fontSize="11"
              fill={hover === i ? "var(--text)" : "var(--text-3)"}
            >
              {p.label}
            </text>
          );
        })}
        {active && hover !== null && (
          <line
            x1={x(hover)}
            x2={x(hover)}
            y1={pad.top}
            y2={pad.top + innerH}
            stroke="var(--border-strong)"
            strokeDasharray="3 3"
          />
        )}
        {segments.map((d) => (
          <path key={d} d={d} fill="none" stroke="var(--series-1)" strokeWidth="2" strokeLinejoin="round" />
        ))}
        {points.map((p, i) =>
          p.value === null ? null : (
            <circle
              key={p.key}
              cx={x(i)}
              cy={y(p.value)}
              r={hover === i ? 5 : points.length > 30 ? 0 : 4}
              fill="var(--series-1)"
              stroke="var(--surface)"
              strokeWidth="2"
            />
          ),
        )}
        {points.map((p, i) => {
          const prev = i > 0 ? x(i - 1) : x(i) - (x(1) - x(0));
          const next = i < points.length - 1 ? x(i + 1) : x(i) + (x(i) - x(i - 1 < 0 ? 0 : i - 1));
          const left = (x(i) + prev) / 2;
          const right = (x(i) + next) / 2;
          return (
            <rect
              key={p.key}
              x={Math.max(pad.left - 10, left)}
              y={pad.top}
              width={Math.max(4, Math.min(right, width) - Math.max(pad.left - 10, left))}
              height={innerH}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
              onFocus={() => setHover(i)}
              tabIndex={0}
              aria-label={`${p.label}: ${p.value === null ? "withheld" : fmtValue(p.value, unit)}`}
            />
          );
        })}
      </svg>
      {active && hover !== null && (
        <div
          className="pointer-events-none absolute top-1 z-10 w-56 rounded-md border border-line bg-surface px-3 py-2 text-[12.5px] shadow-md"
          style={{ left: `clamp(0px, calc(${(x(hover) / width) * 100}% - 112px), calc(100% - 224px))` }}
        >
          <div className="font-medium text-fg">{active.label}</div>
          <div className="tabular text-fg-2">
            {active.value === null ? "Withheld (fewer than 5 people)" : fmtValue(active.value, unit)}
          </div>
          {active.detail && <div className="mt-1 border-t border-line pt-1 text-fg-3">{active.detail}</div>}
        </div>
      )}
    </div>
  );
}

export interface BarItem {
  key: string;
  label: ReactNode;
  value: number | null;
  sub?: ReactNode;
  title?: string;
}

/** Horizontal bars for one measure across categories. Withheld values show as text, no bar. */
export function BarList({
  items,
  unit,
  max,
  labelWidth = "12rem",
  emptyLabel = "No data",
}: {
  items: BarItem[];
  unit: Unit;
  max?: number;
  labelWidth?: string;
  emptyLabel?: string;
}) {
  const [hover, setHover] = useState<string | null>(null);
  if (items.length === 0) return <div className="text-[13px] text-fg-3">{emptyLabel}</div>;
  const top = max ?? Math.max(Number.EPSILON, ...items.map((i) => i.value ?? 0));
  return (
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li
          key={item.key}
          onMouseEnter={() => setHover(item.key)}
          onMouseLeave={() => setHover(null)}
          className="grid items-center gap-3 rounded px-1 py-0.5 text-[13px] hover:bg-surface-2"
          style={{ gridTemplateColumns: `minmax(0, min(${labelWidth}, 42%)) 1fr 5.5rem` }}
          title={item.title}
        >
          <span className="min-w-0">
            <span className="block truncate text-fg-2">{item.label}</span>
            {item.sub && <span className="block truncate text-[11.5px] text-fg-3">{item.sub}</span>}
          </span>
          <span className="relative h-3">
            {item.value !== null && (
              <span
                className="absolute inset-y-0 left-0 rounded-r-[4px]"
                style={{
                  width: `${Math.max(item.value > 0 ? 1.5 : 0, (item.value / top) * 100)}%`,
                  background: "var(--series-1)",
                  opacity: hover && hover !== item.key ? 0.45 : 1,
                }}
              />
            )}
          </span>
          <span className="tabular whitespace-nowrap text-right">
            {item.value === null ? (
              <span className="text-[12px] italic text-fg-3" title="Fewer than 5 people: withheld">
                n&lt;5
              </span>
            ) : (
              <span className="text-fg">{fmtValue(item.value, unit)}</span>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Predicted against observed rates by bucket; points on the diagonal are well calibrated. */
export function CalibrationPlot({
  points,
}: {
  points: { key: string; predicted: number; observed: number; n: number }[];
}) {
  const [hover, setHover] = useState<number | null>(null);
  const size = 320;
  const pad = 40;
  const inner = size - pad - 14;
  const top = Math.max(0.05, ...points.map((p) => Math.max(p.predicted, p.observed))) * 1.1;
  const step = niceStep(top / 4);
  const max = Math.ceil(top / step) * step;
  const sx = (v: number) => pad + (v / max) * inner;
  const sy = (v: number) => 14 + inner - (v / max) * inner;
  const ticks: number[] = [];
  for (let v = 0; v <= max + 1e-9; v += step) ticks.push(v);
  const active = hover !== null ? points[hover] : null;
  return (
    <div className="relative mx-auto max-w-[360px]">
      <svg viewBox={`0 0 ${size} ${size}`} className="h-auto w-full" role="img" aria-label="Calibration">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad} x2={pad + inner} y1={sy(t)} y2={sy(t)} stroke="var(--grid)" />
            <text x={pad - 6} y={sy(t) + 4} textAnchor="end" fontSize="10" fill="var(--text-3)">
              {Math.round(t * 100)}%
            </text>
            <text x={sx(t)} y={14 + inner + 14} textAnchor="middle" fontSize="10" fill="var(--text-3)">
              {Math.round(t * 100)}%
            </text>
          </g>
        ))}
        <line x1={sx(0)} y1={sy(0)} x2={sx(max)} y2={sy(max)} stroke="var(--border-strong)" strokeDasharray="4 4" />
        {points.map((p, i) => (
          <circle
            key={p.key}
            cx={sx(p.predicted)}
            cy={sy(p.observed)}
            r={hover === i ? 6 : 5}
            fill="var(--series-1)"
            stroke="var(--surface)"
            strokeWidth="2"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
        <text x={pad + inner / 2} y={size - 2} textAnchor="middle" fontSize="11" fill="var(--text-2)">
          Predicted
        </text>
        <text x={10} y={14 + inner / 2} textAnchor="middle" fontSize="11" fill="var(--text-2)" transform={`rotate(-90 10 ${14 + inner / 2})`}>
          Observed
        </text>
      </svg>
      {active && (
        <div className="pointer-events-none absolute right-0 top-0 rounded-md border border-line bg-surface px-3 py-2 text-[12.5px] shadow-md">
          <div className="tabular text-fg">
            Predicted {(active.predicted * 100).toFixed(1)}%, observed {(active.observed * 100).toFixed(1)}%
          </div>
          <div className="text-fg-3">{active.n.toLocaleString("en-US")} employee-months</div>
        </div>
      )}
    </div>
  );
}
