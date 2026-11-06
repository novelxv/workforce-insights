"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { BarList } from "@/components/charts";
import { ErrorIcon, LockIcon, WarningIcon } from "@/components/icons";
import {
  Badge,
  Empty,
  ErrorNote,
  Note,
  PageHeader,
  Pagination,
  Panel,
  Select,
  Skeleton,
  Stat,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { fetcher, qs } from "@/lib/api";
import { fmtMonth, fmtTenure } from "@/lib/format";
import { useMe } from "@/lib/session";
import type { RiskEmployee, RiskSummary } from "@/lib/types";

function BandBadge({ band }: { band: RiskEmployee["band"] }) {
  if (band === "high")
    return (
      <Badge tone="critical">
        <ErrorIcon size={12} /> High
      </Badge>
    );
  if (band === "elevated")
    return (
      <Badge tone="warning">
        <WarningIcon size={12} /> Elevated
      </Badge>
    );
  return <Badge>Low</Badge>;
}

function People({ summary }: { summary: RiskSummary }) {
  const [band, setBand] = useState("flagged");
  const [department, setDepartment] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const { data, error } = useSWR<{ employees: RiskEmployee[]; note: string }>(
    `/risk/employees${qs({ band, department, limit: 200 })}`,
    fetcher,
  );
  return (
    <Panel
      title="People to talk to"
      description="Highest probability first. The reasons are the three factors that raise each person's score most."
      actions={
        <>
          <Select
            value={band}
            onChange={(e) => {
              setBand(e.target.value);
              setPage(1);
            }}
            className="h-8 w-36"
            aria-label="Band"
          >
            <option value="flagged">High and elevated</option>
            <option value="high">High only</option>
            <option value="all">Everyone scored</option>
          </Select>
          <Select
            value={department}
            onChange={(e) => {
              setDepartment(e.target.value);
              setPage(1);
            }}
            className="h-8 w-48"
            aria-label="Department"
          >
            <option value="">All departments in scope</option>
            {summary.departments.map((d) => (
              <option key={d.department} value={d.department}>
                {d.department_label}
              </option>
            ))}
          </Select>
        </>
      }
      bodyClassName="p-0"
    >
      {error && (
        <div className="p-4">
          <ErrorNote>{error.message}</ErrorNote>
        </div>
      )}
      {!data && !error && <Skeleton className="m-4 h-64" />}
      {data && data.employees.length === 0 && <Empty title="Nobody in this selection" />}
      {data && data.employees.length > 0 && (
        <>
          <div className="border-b border-line bg-warning-soft/60 px-4 py-2 text-[12.5px] text-fg-2">{data.note}</div>
          <Table>
            <thead>
              <tr>
                <Th>Employee</Th>
                <Th>Department</Th>
                <Th>Grade</Th>
                <Th>Tenure</Th>
                <Th className="text-right">6-month probability</Th>
                <Th>Band</Th>
                <Th>Main reasons</Th>
              </tr>
            </thead>
            <tbody>
              {data.employees.slice((page - 1) * pageSize, page * pageSize).map((e) => (
                <tr key={e.employee_no}>
                  <Td>
                    <div className="font-medium text-fg">{e.name}</div>
                    <div className="font-mono text-[11.5px] text-fg-3">{e.employee_no}</div>
                  </Td>
                  <Td className="text-fg-2">
                    {e.department_label}
                    <div className="text-[11.5px] text-fg-3">{e.location}</div>
                  </Td>
                  <Td className="text-fg-2">
                    {e.grade}
                    {e.employment_type === "PKWT" && <div className="text-[11.5px] text-fg-3">PKWT</div>}
                  </Td>
                  <Td className="whitespace-nowrap text-fg-2">{fmtTenure(e.tenure_months)}</Td>
                  <Td className="tabular text-right">{(e.probability * 100).toFixed(1)}%</Td>
                  <Td>
                    <BandBadge band={e.band} />
                  </Td>
                  <Td>
                    <ul className="space-y-0.5 text-[12.5px] text-fg-2">
                      {e.drivers.map((d) => (
                        <li key={d.feature}>{d.text}</li>
                      ))}
                    </ul>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination page={page} pageSize={pageSize} total={data.employees.length} onPage={setPage} />
        </>
      )}
    </Panel>
  );
}

export function RiskView() {
  const { me } = useMe();
  const { data, error } = useSWR<RiskSummary>("/risk/summary", fetcher);
  if (error) return <ErrorNote>{error.message}</ErrorNote>;
  const top = data?.test_metrics.top_10pct;

  return (
    <div>
      <PageHeader
        title="Attrition risk"
        description={
          data
            ? `Who is more likely than their colleagues to resign in the next ${data.horizon_months} months, scored on ${fmtMonth(data.scored_month)} data by model ${data.model_version}. High is the top 10% of scores, elevated the next 20%.`
            : "Loading…"
        }
      />
      <div className="mb-4">
        <Note tone="warning">
          A score is a reason to have a conversation about pay, workload or career, early. It is not an input to
          performance ratings, promotion, discipline or termination. See the{" "}
          <Link href="/model" className="underline">
            model card
          </Link>{" "}
          for how well it ranks, how it was checked for bias, and its limits.
        </Note>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {data ? (
          <>
            <Stat label="Employees scored" value={data.scored.toLocaleString("en-US")} sub={data.scope ? "In your departments" : "Whole company"} />
            <Stat label="High" value={data.high} sub="Top 10% of scores" tone="critical" />
            <Stat label="Elevated" value={data.elevated} sub="Next 20%" tone="warning" />
            <Stat
              label="Leavers caught by the top 10%"
              value={top ? `${Math.round(top.recall * 100)}%` : "—"}
              sub={top ? `${top.lift.toFixed(1)}× better than picking at random (test month)` : undefined}
            />
          </>
        ) : (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[88px]" />)
        )}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="Share of each department in the high band" description="Departments under 5 people are withheld.">
          {data ? (
            <BarList
              unit="percent"
              items={data.departments.map((d) => ({
                key: d.department,
                label: d.department_label,
                value: d.suppressed ? null : d.high_share,
                sub: d.suppressed ? undefined : `${d.high} of ${d.scored}`,
              }))}
            />
          ) : (
            <Skeleton className="h-80" />
          )}
        </Panel>
        <Panel
          title="What raises the flagged scores"
          description={data ? `Share of the ${data.flagged} high and elevated scores where each factor is one of the top three reasons.` : undefined}
        >
          {data ? (
            <BarList
              unit="percent"
              max={1}
              items={data.drivers.map((d) => ({ key: d.feature, label: d.label, value: d.share, sub: `${d.count} people` }))}
            />
          ) : (
            <Skeleton className="h-80" />
          )}
        </Panel>
      </div>

      <div className="mt-4">
        {me?.sees_individuals && data && <People summary={data} />}
        {me && !me.sees_individuals && (
          <Panel>
            <div className="flex items-start gap-3 text-[13px] text-fg-2">
              <LockIcon size={18} className="mt-0.5 shrink-0 text-fg-3" />
              <div>
                Individual scores are visible to HR analytics admins and to HR business partners for their own
                departments. Leaders see the aggregates above, so that a score never reaches the person deciding a
                rating or a promotion.
              </div>
            </div>
          </Panel>
        )}
      </div>
    </div>
  );
}
