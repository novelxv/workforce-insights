"use client";

import Link from "next/link";
import useSWR from "swr";

import { BarList, TrendLine } from "@/components/charts";
import { DownloadIcon } from "@/components/icons";
import { exploreHref } from "@/components/result";
import { ErrorNote, LinkButton, PageHeader, Panel, Skeleton, cx } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { fmtChange, fmtMonth, fmtNumber, fmtValue } from "@/lib/format";
import { useMeta } from "@/lib/session";
import type { Dashboard, Kpi, QueryResult } from "@/lib/types";

function Arrow({ up }: { up: boolean }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden className="shrink-0">
      <path d={up ? "M6 2 10 8H2z" : "M6 10 2 4h8z"} fill="currentColor" />
    </svg>
  );
}

function KpiTile({ kpi, previousLabel }: { kpi: Kpi; previousLabel: string }) {
  const delta = kpi.value !== null && kpi.previous !== null ? kpi.value - kpi.previous : null;
  // Better or worse only for metrics with a direction; others change neutrally.
  const tone =
    delta === null || delta === 0 || kpi.higher_is_better === null
      ? "neutral"
      : delta > 0 === kpi.higher_is_better
        ? "good"
        : "critical";
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3" title={kpi.definition}>
      <div className="text-[13px] text-fg-2">{kpi.label}</div>
      <div className="tabular mt-1 text-[26px] font-semibold leading-tight text-fg">{fmtValue(kpi.value, kpi.unit)}</div>
      <div className="mt-1 flex flex-wrap items-center gap-x-1 text-[12px]">
        {delta !== null && (
          <span
            className={cx(
              "tabular inline-flex items-center gap-1 font-medium",
              tone === "good" && "text-good",
              tone === "critical" && "text-critical",
              tone === "neutral" && "text-fg-2",
            )}
          >
            {delta !== 0 && <Arrow up={delta > 0} />}
            {fmtChange(delta, kpi.unit)}
          </span>
        )}
        <span className="whitespace-nowrap text-fg-3">vs {previousLabel}</span>
      </div>
    </div>
  );
}

function DefinitionLine({ result }: { result: QueryResult }) {
  return (
    <span>
      {result.metric.definition}{" "}
      <Link href={exploreHref(result.spec)} className="text-link hover:underline">
        Explore
      </Link>
    </span>
  );
}

function bars(result: QueryResult, dim: string) {
  return result.rows.map((r) => ({
    key: String(r[dim]),
    label: String(r[`${dim}_label`]),
    value: r.suppressed ? null : r.value,
    title: `${fmtNumber(r.population)} people`,
  }));
}

function trend(result: QueryResult) {
  return result.rows.map((r) => ({
    key: String(r.month),
    label: String(r.month_label),
    value: r.suppressed ? null : r.value,
  }));
}

export function OverviewView() {
  const { data, error } = useSWR<Dashboard>("/dashboard", fetcher);
  const { meta } = useMeta();

  if (error) return <ErrorNote>{error.message}</ErrorNote>;
  const scopeText = data?.scope
    ? `Your departments: ${data.scope
        .map((c) => meta?.dimensions.find((d) => d.key === "department")?.values?.find((v) => v.code === c)?.label ?? c)
        .join(", ")}.`
    : "Whole company.";
  const prevLabel = data
    ? `${fmtMonth(data.previous_period.start)} – ${fmtMonth(data.previous_period.end)}`
    : "";

  return (
    <div>
      <PageHeader
        title="Workforce overview"
        description={
          data
            ? `12 months to ${fmtMonth(data.period.end)}, against the 12 months before. ${scopeText}`
            : "Loading…"
        }
        actions={
          <LinkButton href="/api/exports/monthly-report.xlsx" download>
            <DownloadIcon size={15} /> Monthly report (.xlsx)
          </LinkButton>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {data
          ? data.kpis.map((k) => (
              <KpiTile
                key={k.key}
                kpi={k}
                previousLabel={["headcount", "avg_tenure_years", "female_share"].includes(k.key) ? fmtMonth(data.previous_period.end) : "prior 12 mo"}
              />
            ))
          : Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[92px]" />)}
      </div>
      {data && <p className="mt-2 text-[12px] text-fg-3">Prior 12 months: {prevLabel}. Hover a tile for its definition.</p>}

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <Panel title="Headcount at month end" description={data ? <DefinitionLine result={data.headcount_trend} /> : null}>
          {data ? (
            <TrendLine unit="count" points={trend(data.headcount_trend)} ariaLabel="Headcount by month" />
          ) : (
            <Skeleton className="h-52" />
          )}
        </Panel>
        <Panel title="Resignations per month" description={data ? <DefinitionLine result={data.resignations_trend} /> : null}>
          {data ? (
            <TrendLine unit="count" fromZero points={trend(data.resignations_trend)} ariaLabel="Resignations by month" />
          ) : (
            <Skeleton className="h-52" />
          )}
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <Panel
          title="Voluntary turnover by department"
          description={data ? <DefinitionLine result={data.turnover_by_department} /> : null}
        >
          {data ? (
            <BarList unit="percent" items={bars(data.turnover_by_department, "department")} labelWidth="12rem" />
          ) : (
            <Skeleton className="h-80" />
          )}
        </Panel>
        <div className="space-y-4">
          <Panel title="Voluntary turnover by tenure" description="Annualised, last 12 months. Attributes as they were in each month.">
            {data ? <BarList unit="percent" items={bars(data.turnover_by_tenure, "tenure_band")} labelWidth="5rem" /> : <Skeleton className="h-32" />}
          </Panel>
          <Panel title="Voluntary turnover by age" description="Annualised, last 12 months.">
            {data ? <BarList unit="percent" items={bars(data.turnover_by_age, "age_band")} labelWidth="5rem" /> : <Skeleton className="h-32" />}
          </Panel>
        </div>
      </div>
    </div>
  );
}
