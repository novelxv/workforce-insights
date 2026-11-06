"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import useSWR from "swr";

import { ResultView } from "@/components/result";
import { Button, ErrorNote, Field, Input, PageHeader, Panel, Select, Skeleton, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/session";
import type { Filter, Meta, QueryResult, Spec } from "@/lib/types";

function monthInput(iso: string) {
  return iso.slice(0, 7);
}

function addMonths(ym: string, n: number): string {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + n, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

function defaultSpec(meta: Meta): Spec {
  const end = monthInput(meta.last_month);
  return {
    metric: "voluntary_turnover_rate",
    dimensions: ["department"],
    filters: [],
    period: { start: addMonths(end, -11), end },
    order: "value_desc",
    limit: null,
  };
}

function parseSpec(raw: string | null): Spec | null {
  if (!raw) return null;
  try {
    const s = JSON.parse(raw) as Spec;
    return {
      ...s,
      period: { start: s.period.start.slice(0, 7), end: s.period.end.slice(0, 7) },
      filters: s.filters ?? [],
      dimensions: s.dimensions ?? [],
    };
  } catch {
    return null;
  }
}

function FilterRow({
  meta,
  filter,
  used,
  onChange,
  onRemove,
}: {
  meta: Meta;
  filter: Filter;
  used: string[];
  onChange: (f: Filter) => void;
  onRemove: () => void;
}) {
  const dims = meta.dimensions.filter((d) => !d.time && (d.key === filter.dimension || !used.includes(d.key)));
  const values = meta.dimensions.find((d) => d.key === filter.dimension)?.values ?? [];
  return (
    <div className="rounded-md border border-line p-2.5">
      <div className="flex items-center gap-2">
        <Select
          value={filter.dimension}
          onChange={(e) => onChange({ dimension: e.target.value, values: [] })}
          aria-label="Filter on"
          className="h-8"
        >
          {dims.map((d) => (
            <option key={d.key} value={d.key}>
              {d.label}
            </option>
          ))}
        </Select>
        <Button size="sm" variant="ghost" onClick={onRemove} aria-label="Remove filter">
          Remove
        </Button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {values.map((v) => {
          const on = filter.values.includes(v.code);
          return (
            <button
              key={v.code}
              type="button"
              aria-pressed={on}
              onClick={() =>
                onChange({
                  ...filter,
                  values: on ? filter.values.filter((x) => x !== v.code) : [...filter.values, v.code],
                })
              }
              className={cx(
                "rounded border px-2 py-0.5 text-[12px]",
                on ? "border-ink bg-ink-soft text-ink" : "border-line-strong text-fg-2 hover:bg-surface-2",
              )}
            >
              {v.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function ExploreView() {
  const { meta } = useMeta();
  const params = useSearchParams();
  const router = useRouter();
  // The link carries the spec that was last run, so a query can be shared or bookmarked.
  const linked = useMemo(() => parseSpec(params.get("spec")), [params]);
  const submitted = meta ? (linked ?? defaultSpec(meta)) : null;
  const [edited, setSpec] = useState<Spec | null>(null);
  const spec = edited ?? submitted;
  const { data: result, error: queryError, isValidating: busy } = useSWR<QueryResult>(
    submitted ? ["/query", JSON.stringify(submitted)] : null,
    () => api.post<QueryResult>("/query", submitted),
    { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  const error = queryError instanceof Error ? queryError.message : null;

  function run(s: Spec) {
    const cleaned = { ...s, filters: s.filters.filter((f) => f.values.length > 0) };
    router.replace(`/explore?spec=${encodeURIComponent(JSON.stringify(cleaned))}`, { scroll: false });
  }

  if (!meta || !spec) {
    return (
      <div>
        <PageHeader title="Explore" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  const metric = meta.metrics.find((m) => m.key === spec.metric);
  const breakdowns = meta.dimensions;
  const set = (patch: Partial<Spec>) => setSpec({ ...spec, ...patch });
  const setDim = (i: number, key: string) => {
    const dims = [...spec.dimensions];
    if (key) dims[i] = key;
    else dims.splice(i, 1);
    set({ dimensions: dims.filter(Boolean) });
  };
  const usedFilterDims = spec.filters.map((f) => f.dimension);
  const nextFilterDim = breakdowns.find((d) => !d.time && !usedFilterDims.includes(d.key));

  return (
    <div>
      <PageHeader
        title="Explore"
        description="Build a query from the defined metrics. The same compiler, checks and small-group rule as Ask and the dashboard."
      />
      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        <Panel title="Query">
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              run(spec);
            }}
          >
            <Field label="Metric" hint={metric?.definition}>
              <Select value={spec.metric} onChange={(e) => set({ metric: e.target.value })}>
                {meta.metrics.map((m) => (
                  <option key={m.key} value={m.key}>
                    {m.label}
                  </option>
                ))}
              </Select>
            </Field>
            {[0, 1].map((i) => (
              <Field key={i} label={i === 0 ? "Break down by" : "Then by"}>
                <Select
                  value={spec.dimensions[i] ?? ""}
                  onChange={(e) => setDim(i, e.target.value)}
                  disabled={i === 1 && spec.dimensions.length === 0}
                >
                  <option value="">{i === 0 ? "Nothing (one figure)" : "Nothing"}</option>
                  {breakdowns
                    .filter((d) => !spec.dimensions.some((x, j) => j !== i && x === d.key))
                    .map((d) => (
                      <option key={d.key} value={d.key}>
                        {d.label}
                      </option>
                    ))}
                </Select>
              </Field>
            ))}
            <div className="grid grid-cols-2 gap-2">
              <Field label="From">
                <Input
                  type="month"
                  value={spec.period.start}
                  min={monthInput(meta.first_month)}
                  max={spec.period.end}
                  onChange={(e) => set({ period: { ...spec.period, start: e.target.value } })}
                />
              </Field>
              <Field label="To">
                <Input
                  type="month"
                  value={spec.period.end}
                  min={spec.period.start}
                  max={monthInput(meta.last_month)}
                  onChange={(e) => set({ period: { ...spec.period, end: e.target.value } })}
                />
              </Field>
            </div>
            {metric?.point_in_time && !spec.dimensions.some((d) => ["month", "quarter", "year"].includes(d)) && (
              <p className="text-[12px] text-fg-3">{metric.label} is measured at the end of the period.</p>
            )}
            <div>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[13px] font-medium text-fg-2">Filters</span>
                {nextFilterDim && spec.filters.length < 4 && (
                  <button
                    type="button"
                    className="text-[12.5px] text-link hover:underline"
                    onClick={() => set({ filters: [...spec.filters, { dimension: nextFilterDim.key, values: [] }] })}
                  >
                    Add filter
                  </button>
                )}
              </div>
              <div className="space-y-2">
                {spec.filters.length === 0 && <p className="text-[12.5px] text-fg-3">None</p>}
                {spec.filters.map((f, i) => (
                  <FilterRow
                    key={`${f.dimension}-${i}`}
                    meta={meta}
                    filter={f}
                    used={usedFilterDims}
                    onChange={(nf) => set({ filters: spec.filters.map((x, j) => (j === i ? nf : x)) })}
                    onRemove={() => set({ filters: spec.filters.filter((_, j) => j !== i) })}
                  />
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Sort">
                <Select
                  value={spec.order ?? ""}
                  onChange={(e) => set({ order: (e.target.value || null) as Spec["order"] })}
                  disabled={spec.dimensions.length === 0}
                >
                  <option value="">Natural order</option>
                  <option value="value_desc">Highest first</option>
                  <option value="value_asc">Lowest first</option>
                </Select>
              </Field>
              <Field label="Keep top">
                <Input
                  type="number"
                  min={1}
                  max={50}
                  value={spec.limit ?? ""}
                  placeholder="All"
                  onChange={(e) => set({ limit: e.target.value ? Number(e.target.value) : null })}
                  disabled={spec.dimensions.length === 0}
                />
              </Field>
            </div>
            <Button type="submit" variant="primary" className="w-full" disabled={busy}>
              {busy ? "Running…" : "Run"}
            </Button>
          </form>
        </Panel>

        <div className="min-w-0">
          <ErrorNote>{error}</ErrorNote>
          {result && (
            <Panel title={result.description} description={`${result.metric.definition} Calculated as ${result.metric.formula}.`}>
              <ResultView result={result} showExplore={false} />
            </Panel>
          )}
          {!result && !error && <Skeleton className="h-80" />}
        </div>
      </div>
    </div>
  );
}
