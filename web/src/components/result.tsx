"use client";

import Link from "next/link";
import { useState } from "react";

import { fmtNumber, fmtValue } from "@/lib/format";
import type { QueryResult, Spec } from "@/lib/types";
import { BarList, TrendLine } from "./charts";
import { InfoIcon } from "./icons";
import { Mono, Table, Tabs, Td, Th, cx } from "./ui";

const TIME = new Set(["month", "quarter", "year"]);

export function exploreHref(spec: Spec): string {
  return `/explore?spec=${encodeURIComponent(JSON.stringify(spec))}`;
}

function label(row: QueryResult["rows"][number], dim: string): string {
  return String(row[`${dim}_label`] ?? row[dim] ?? "");
}

function Withheld() {
  return (
    <span className="text-[12px] italic text-fg-3" title="Fewer than 5 people: withheld">
      n&lt;5
    </span>
  );
}

function Chart({ result }: { result: QueryResult }) {
  const { metric, dimensions, rows } = result;
  if (dimensions.length === 0) {
    const row = rows[0];
    return (
      <div className="py-2">
        <div className="tabular text-[34px] font-semibold leading-tight text-fg">
          {row.suppressed ? <Withheld /> : fmtValue(row.value, metric.unit)}
        </div>
        <div className="mt-1 text-[12.5px] text-fg-3">
          {metric.point_in_time ? "Based on " : "Across "}
          {fmtNumber(row.population)} {row.population === 1 ? "person" : "people"}
        </div>
      </div>
    );
  }
  if (dimensions.length === 1) {
    const d = dimensions[0].key;
    if (TIME.has(d)) {
      return (
        <TrendLine
          unit={metric.unit}
          fromZero={metric.unit === "count"}
          ariaLabel={result.description}
          points={rows.map((r) => ({
            key: String(r[d]),
            label: label(r, d),
            value: r.suppressed ? null : r.value,
            detail: `${fmtNumber(r.population)} people`,
          }))}
        />
      );
    }
    return (
      <BarList
        unit={metric.unit}
        items={rows.map((r) => ({
          key: String(r[d]),
          label: label(r, d),
          value: r.suppressed ? null : r.value,
          title: `${label(r, d)}: ${r.suppressed ? "withheld" : fmtValue(r.value, metric.unit)}, ${fmtNumber(r.population)} people`,
        }))}
      />
    );
  }
  return <Pivot result={result} />;
}

/** Two dimensions: the first down the side, the second across. */
function Pivot({ result }: { result: QueryResult }) {
  const [a, b] = result.dimensions.map((d) => d.key);
  const rowsKeys: string[] = [];
  const colKeys: string[] = [];
  const labels: Record<string, string> = {};
  const cells = new Map<string, QueryResult["rows"][number]>();
  for (const r of result.rows) {
    const ra = String(r[a]);
    const cb = String(r[b]);
    if (!rowsKeys.includes(ra)) rowsKeys.push(ra);
    if (!colKeys.includes(cb)) colKeys.push(cb);
    labels[`a:${ra}`] = label(r, a);
    labels[`b:${cb}`] = label(r, b);
    cells.set(`${ra}|${cb}`, r);
  }
  return (
    <Table>
      <thead>
        <tr>
          <Th>{result.dimensions[0].label}</Th>
          {colKeys.map((c) => (
            <Th key={c} className="text-right">
              {labels[`b:${c}`]}
            </Th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rowsKeys.map((r) => (
          <tr key={r}>
            <Td className="text-fg-2">{labels[`a:${r}`]}</Td>
            {colKeys.map((c) => {
              const cell = cells.get(`${r}|${c}`);
              return (
                <Td key={c} className="tabular text-right">
                  {!cell ? "—" : cell.suppressed ? <Withheld /> : fmtValue(cell.value, result.metric.unit)}
                </Td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

function Rows({ result }: { result: QueryResult }) {
  return (
    <Table>
      <thead>
        <tr>
          {result.dimensions.map((d) => (
            <Th key={d.key}>{d.label}</Th>
          ))}
          <Th className="text-right">{result.metric.label}</Th>
          <Th className="text-right">People</Th>
        </tr>
      </thead>
      <tbody>
        {result.rows.map((r, i) => (
          <tr key={i}>
            {result.dimensions.map((d) => (
              <Td key={d.key} className="text-fg-2">
                {label(r, d.key)}
              </Td>
            ))}
            <Td className="tabular text-right">{r.suppressed ? <Withheld /> : fmtValue(r.value, result.metric.unit)}</Td>
            <Td className="tabular text-right text-fg-3">{fmtNumber(r.population)}</Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export function ResultView({ result, showExplore = true }: { result: QueryResult; showExplore?: boolean }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const hasDims = result.dimensions.length > 0;
  return (
    <div>
      {hasDims && (
        <div className="mb-3">
          <Tabs
            value={view}
            onChange={setView}
            tabs={[
              { id: "chart", label: result.dimensions.length === 2 ? "Grid" : "Chart" },
              { id: "table", label: "Table" },
            ]}
          />
        </div>
      )}
      {view === "chart" ? <Chart result={result} /> : <Rows result={result} />}
      {result.suppressed > 0 && (
        <p className="mt-3 flex items-start gap-1.5 text-[12.5px] text-fg-3">
          <InfoIcon size={14} className="mt-0.5 shrink-0" />
          {result.suppressed === 1 ? "One value is" : `${result.suppressed} values are`} withheld: each rests on
          fewer than 5 people, or would let a withheld value be worked out from a total.
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-start gap-x-4 gap-y-2 border-t border-line pt-3 text-[12.5px]">
        <details className="min-w-0 flex-1">
          <summary className="text-link hover:underline">Compiled SQL</summary>
          <pre className="mt-2 overflow-x-auto rounded-md bg-surface-3 px-3 py-2 font-mono text-[11.5px] leading-relaxed text-fg-2">
            {result.sql}
          </pre>
          <div className="mt-1.5 text-fg-3">
            Parameters:{" "}
            <Mono className="text-fg-2">
              {Object.entries(result.params)
                .map(([k, v]) => `${k} = ${JSON.stringify(v)}`)
                .join(", ")}
            </Mono>
          </div>
        </details>
        {showExplore && (
          <Link href={exploreHref(result.spec)} className={cx("text-link hover:underline")}>
            Open in Explore
          </Link>
        )}
      </div>
    </div>
  );
}
