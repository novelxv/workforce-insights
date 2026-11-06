"use client";

import { useState } from "react";

import { DownloadIcon, LockIcon } from "@/components/icons";
import { Badge, ErrorNote, Field, LinkButton, PageHeader, Panel, Select, Skeleton, Table, Td, Th } from "@/components/ui";
import { fmtMonth } from "@/lib/format";
import { useMe, useMeta } from "@/lib/session";

function months(first: string, last: string): string[] {
  const out: string[] = [];
  const d = new Date(`${last.slice(0, 7)}-01T00:00:00Z`);
  const stop = new Date(`${first.slice(0, 7)}-01T00:00:00Z`);
  while (d >= stop) {
    out.push(d.toISOString().slice(0, 7));
    d.setUTCMonth(d.getUTCMonth() - 1);
  }
  return out;
}

const UNIT_LABEL = { count: "Count", percent: "Percent", years: "Years", hours: "Hours", ratio: "Ratio" };

export function DefinitionsView() {
  const { meta, error } = useMeta();
  const { me } = useMe();
  const [month, setMonth] = useState("");
  if (error) return <ErrorNote>{error.message}</ErrorNote>;
  const options = meta ? months(meta.first_month, meta.last_month) : [];
  const chosen = month || options[0] || "";

  return (
    <div>
      <PageHeader
        title="Definitions and exports"
        description="Every figure in the app, the Excel report and the Power BI measures comes from these definitions."
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Monthly HR report" description="Excel workbook: summary against last month and last year, monthly trend with trailing 12-month turnover as live formulas, a department table, and these definitions.">
          {meta ? (
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Month" className="w-44">
                <Select value={chosen} onChange={(e) => setMonth(e.target.value)}>
                  {options.map((m) => (
                    <option key={m} value={m}>
                      {fmtMonth(`${m}-01`)}
                    </option>
                  ))}
                </Select>
              </Field>
              <LinkButton href={`/api/exports/monthly-report.xlsx?month=${chosen}`} variant="primary" download>
                <DownloadIcon size={15} /> Download .xlsx
              </LinkButton>
              <p className="w-full text-[12.5px] text-fg-3">
                {meta.scope ? "Limited to your departments. " : ""}Values resting on fewer than {meta.min_group_size} people
                show as n&lt;5.
              </p>
            </div>
          ) : (
            <Skeleton className="h-16" />
          )}
        </Panel>
        <Panel title="Power BI extract" description="Star-schema CSVs, the metrics as DAX measures, and a setup guide (relationships, types, small-group measures).">
          {me?.role === "HR_ADMIN" ? (
            <div className="space-y-2">
              <LinkButton href="/api/exports/powerbi.zip" download>
                <DownloadIcon size={15} /> Download .zip
              </LinkButton>
              <p className="text-[12.5px] text-fg-3">
                Pseudonymous: employee numbers only, no names, dates of birth or salaries (pay appears as the ratio to
                the grade midpoint), no individual risk scores.
              </p>
            </div>
          ) : (
            <div className="flex items-start gap-2 text-[13px] text-fg-2">
              <LockIcon size={16} className="mt-0.5 shrink-0 text-fg-3" />
              Row-level extracts are for HR analytics admins. They hold one row per employee per month.
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Metrics" className="mt-4" bodyClassName="p-0">
        {meta ? (
          <Table>
            <thead>
              <tr>
                <Th>Metric</Th>
                <Th>Definition</Th>
                <Th>Calculation</Th>
                <Th>Measured</Th>
              </tr>
            </thead>
            <tbody>
              {meta.metrics.map((m) => (
                <tr key={m.key}>
                  <Td className="whitespace-nowrap">
                    <div className="font-medium text-fg">{m.label}</div>
                    <div className="mt-0.5 flex gap-1">
                      <Badge>{UNIT_LABEL[m.unit]}</Badge>
                      <code className="font-mono text-[11px] text-fg-3">{m.key}</code>
                    </div>
                  </Td>
                  <Td className="max-w-md text-fg-2">{m.definition}</Td>
                  <Td className="max-w-sm text-[12.5px] text-fg-2">{m.formula}</Td>
                  <Td className="whitespace-nowrap text-fg-3">{m.point_in_time ? "End of period" : "Across period"}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <Skeleton className="m-4 h-96" />
        )}
      </Panel>

      <Panel title="Breakdowns and filters" className="mt-4">
        {meta ? (
          <dl className="grid gap-x-6 gap-y-3 text-[13px] sm:grid-cols-2">
            {meta.dimensions.map((d) => (
              <div key={d.key}>
                <dt className="font-medium text-fg">{d.label}</dt>
                <dd className="text-fg-2">
                  {d.time
                    ? `Breakdown only. Data from ${fmtMonth(meta.first_month)} to ${fmtMonth(meta.last_month)}.`
                    : d.values?.map((v) => v.label).join(", ")}
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <Skeleton className="h-40" />
        )}
        <p className="mt-4 text-[12.5px] text-fg-3">
          Attributes are as they were in each month: someone who moved from Claims to IT counts in Claims before the
          move and in IT after it. Data starts two months after the simulation does, once hires have caught up with
          the exits of the opening workforce.
        </p>
      </Panel>
    </div>
  );
}
