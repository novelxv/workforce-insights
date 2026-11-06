"use client";

import useSWR from "swr";

import { TrendLine } from "@/components/charts";
import { ErrorNote, PageHeader, Panel, Skeleton, Table, Td, Th } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { fmtNumber } from "@/lib/format";
import type { Cohorts } from "@/lib/types";

/** One hue, light to dark: darker cells kept more of their hires. */
function shade(v: number) {
  const t = Math.min(0.85, Math.max(0.08, (v - 0.35) / 0.65)) * 100;
  return {
    background: `color-mix(in oklab, var(--series-1) ${t.toFixed(0)}%, var(--surface))`,
    color: t > 55 ? "#fff" : "var(--text)",
  };
}

export function RetentionView() {
  const { data, error } = useSWR<Cohorts>("/cohorts", fetcher);
  if (error) return <ErrorNote>{error.message}</ErrorNote>;

  const pooled = data
    ? [{ months: 0, retained: 1, hires: 0 }, ...data.pooled].map((p) => ({
        key: String(p.months),
        label: p.months === 0 ? "Start" : `${p.months} mo`,
        value: p.retained,
        detail: p.months === 0 ? "Everyone hired is employed" : `${fmtNumber(p.hires)} hires old enough to count`,
      }))
    : [];

  return (
    <div>
      <PageHeader
        title="Retention of new hires"
        description="Share of each quarter's hires still employed 3, 6, 9, 12, 18 and 24 months after their start date. A cohort only counts at a checkpoint once all of it has reached that point; until then the cell is empty, not zero."
      />
      <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
        <Panel
          title="All cohorts together"
          description="Hires from every quarter that had reached each checkpoint, pooled. Horizontal spacing is to scale."
        >
          {data ? (
            <TrendLine
              unit="percent"
              fromZero
              xs={[0, ...data.pooled.map((p) => p.months)]}
              points={pooled}
              ariaLabel="Pooled retention curve"
              height={260}
            />
          ) : (
            <Skeleton className="h-60" />
          )}
          {data && data.pooled.find((p) => p.months === 12)?.retained != null && (
            <p className="mt-2 text-[13px] text-fg-2">
              {Math.round((1 - (data.pooled.find((p) => p.months === 12)!.retained ?? 0)) * 100)}% of hires left within a
              year. First-year exits point at hiring and onboarding more than at pay or careers.
            </p>
          )}
        </Panel>
        <Panel title="By hire quarter" bodyClassName="p-0">
          {data ? (
            <Table>
              <thead>
                <tr>
                  <Th>Hired in</Th>
                  <Th className="text-right">Hires</Th>
                  {data.checkpoints.map((c) => (
                    <Th key={c} className="text-center">
                      {c} mo
                    </Th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.cohorts.map((c) => (
                  <tr key={c.cohort}>
                    <Td className="whitespace-nowrap text-fg-2">{c.label}</Td>
                    <Td className="tabular text-right text-fg-3">{c.hires}</Td>
                    {c.points.map((p) => (
                      <td key={p.months} className="border-b border-line p-0.5">
                        {c.suppressed ? (
                          <div className="py-1.5 text-center text-[12px] italic text-fg-3">n&lt;5</div>
                        ) : p.retained === null ? (
                          <div className="py-1.5 text-center text-fg-3" title="Not reached yet">
                            ·
                          </div>
                        ) : (
                          <div
                            className="tabular rounded-[3px] py-1.5 text-center text-[12.5px]"
                            style={shade(p.retained)}
                            title={`${c.label} hires still employed after ${p.months} months: ${(p.retained * 100).toFixed(1)}%`}
                          >
                            {Math.round(p.retained * 100)}%
                          </div>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <Skeleton className="m-4 h-72" />
          )}
        </Panel>
      </div>
    </div>
  );
}
