"use client";

import useSWR from "swr";

import { BarList, CalibrationPlot } from "@/components/charts";
import { ErrorNote, Mono, PageHeader, Panel, Skeleton, Stat, Table, Td, Th } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { fmtDateTime, fmtMonth, fmtNumber } from "@/lib/format";
import type { FairnessGroup, ModelCard } from "@/lib/types";

const pct = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`);

function genderRecall(groups: FairnessGroup[]): string {
  const f = groups.find((g) => g.group === "F")?.recall;
  const m = groups.find((g) => g.group === "M")?.recall;
  if (f == null || m == null) return "";
  const gap = Math.abs(f - m) >= 0.05 ? " That gap is worth investigating before the list is used." : "";
  return `Of the people who resigned, ${pct(f, 0)} of women and ${pct(m, 0)} of men had been flagged.${gap} `;
}

/** How much of the way from the random baseline to the ceiling a score has come. */
const share = (score: number, random: number, ceiling: number) =>
  ceiling > random ? `${Math.round(((score - random) / (ceiling - random)) * 100)}%` : "—";

function FairnessTable({ title, groups, ratio }: { title: string; groups: FairnessGroup[]; ratio: number | null }) {
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-[13.5px] font-semibold">{title}</h3>
        <span className="text-[12px] text-fg-3">
          Flag-rate ratio, smallest to largest group of 100+: {ratio === null ? "—" : ratio.toFixed(2)}
        </span>
      </div>
      <Table>
        <thead>
          <tr>
            <Th>Group</Th>
            <Th className="text-right">Employee-months</Th>
            <Th className="text-right">Resigned within 6 months</Th>
            <Th className="text-right">Mean predicted</Th>
            <Th className="text-right">Flagged</Th>
            <Th className="text-right">Leavers flagged</Th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => (
            <tr key={g.group}>
              <Td className="text-fg-2">{g.group === "F" ? "Women" : g.group === "M" ? "Men" : g.group}</Td>
              <Td className="tabular text-right text-fg-3">{fmtNumber(g.n)}</Td>
              <Td className="tabular text-right">{pct(g.observed_rate)}</Td>
              <Td className="tabular text-right">{pct(g.mean_predicted)}</Td>
              <Td className="tabular text-right">{pct(g.flag_rate)}</Td>
              <Td className="tabular text-right">{pct(g.recall, 0)}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}

export function ModelView() {
  const { data, error } = useSWR<ModelCard>("/model", fetcher);
  if (error) return <ErrorNote>{error.message}</ErrorNote>;
  if (!data) {
    return (
      <div>
        <PageHeader title="Model card" />
        <Skeleton className="h-96" />
      </div>
    );
  }
  const m = data.metrics;
  const pit = m.point_in_time;

  return (
    <div>
      <PageHeader
        title="Model card: voluntary attrition risk"
        description={
          <>
            <Mono>{data.version}</Mono>, trained {fmtDateTime(data.trained_at)} WIB. LightGBM on monthly snapshots,
            Platt calibration, explanations from TreeSHAP contributions. Trained and tested on simulated data, so
            the true causes of attrition are known and the model can be checked against them.
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="ROC-AUC, test months" value={m.roc_auc.toFixed(3)} sub={`Ceiling ${m.ceiling.roc_auc.toFixed(3)} · random 0.5`} />
        <Stat label="PR-AUC, test months" value={m.pr_auc.toFixed(3)} sub={`Ceiling ${m.ceiling.pr_auc.toFixed(3)} · base rate ${m.base_rate.toFixed(3)}`} />
        <Stat
          label="Top 10% catches"
          value={pct(pit.top_10pct.recall, 0)}
          sub={`of ${pit.leavers_next_6m} leavers, ${pit.top_10pct.lift.toFixed(2)}× lift (${fmtMonth(pit.month)})`}
        />
        <Stat label="Brier score" value={m.brier_calibrated.toFixed(4)} sub={`${m.brier_raw.toFixed(4)} before calibration`} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="How to read these numbers">
          <div className="space-y-2.5 text-[13px] text-fg-2">
            <p>
              <strong className="font-medium text-fg">The ceiling</strong> ranks the same test rows with the formula
              that generated the data, which no real HR team would have, minus each person&apos;s unobserved
              propensity to leave. Of the distance from a random ranking to the ceiling, the model covers{" "}
              {share(m.roc_auc, 0.5, m.ceiling.roc_auc)} on ROC-AUC and {share(m.pr_auc, m.base_rate, m.ceiling.pr_auc)} on
              PR-AUC, so there is room left in finding the riskiest few. The gap between the ceiling and a perfect score
              is randomness in who decides to resign, not something better modelling could recover.
            </p>
            <p>
              <strong className="font-medium text-fg">In use</strong>, one month is scored and HR looks at the top 10%.
              In the test month ({fmtMonth(pit.month)}), {pit.top_10pct.flagged} people were flagged and{" "}
              {pct(pit.top_10pct.precision, 0)} of them resigned within six months, against a base rate of{" "}
              {pct(pit.leavers_next_6m / pit.employees, 1)}.
            </p>
            <p>
              <strong className="font-medium text-fg">Probabilities run low.</strong> They average{" "}
              {pct(m.mean_predicted)} on the test months against {pct(m.base_rate)} observed, because the calibration
              was fitted on months when {pct(m.valid_base_rate)} resigned. The ranking is unaffected; read the
              probabilities as relative, or recalibrate on recent months.
            </p>
            <p>
              <strong className="font-medium text-fg">Split by time.</strong> Trained on {fmtNumber(m.rows.train)},
              tuned on {fmtNumber(m.rows.valid)} and tested on {fmtNumber(m.rows.test)} employee-months, each block
              later than the one before, so nothing from the future leaks into training.
            </p>
          </div>
        </Panel>
        <Panel title="Calibration" description="Test months in ten equal groups by score. On the dashed line, predicted equals observed.">
          <CalibrationPlot
            points={data.calibration.map((c) => ({ key: String(c.bucket), predicted: c.predicted, observed: c.observed, n: c.n }))}
          />
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <Panel title="What drives the scores" description="Mean absolute TreeSHAP contribution on the test months (log-odds).">
          <BarList
            unit="ratio"
            items={data.importance.map((i) => ({ key: i.feature, label: i.label, value: i.mean_abs_shap, sub: `${pct(i.gain_share, 0)} of split gain` }))}
          />
          <p className="mt-3 text-[12.5px] text-fg-3">
            Gender and age are not model inputs. They are used only in the audit on the right.
          </p>
        </Panel>
        <Panel
          title="Bias audit"
          description={`Flags are the top 10% of scores on the test months (raw score above ${data.fairness.threshold_top_10pct.toFixed(3)}). Equal flag rates are not the aim when underlying rates differ; the check is whether predictions track what happened in each group.`}
        >
          <div className="space-y-5">
            <FairnessTable title="Gender" groups={data.fairness.gender.groups} ratio={data.fairness.gender.flag_rate_ratio_min_max} />
            <FairnessTable title="Age band" groups={data.fairness.age_band.groups} ratio={data.fairness.age_band.flag_rate_ratio_min_max} />
            <p className="text-[12.5px] text-fg-2">
              {genderRecall(data.fairness.gender.groups)}
              Younger staff are flagged more often because they resign more often and are earlier in their tenure, which
              the model uses. Where mean predicted sits well below the observed rate for a group, the model
              under-predicts for that group; that gap, not the flag rate, is what to watch when retraining.
            </p>
          </div>
        </Panel>
      </div>

      <Panel title="Limits" className="mt-4">
        <ul className="list-disc space-y-1.5 pl-4 text-[13px] text-fg-2">
          <li>Simulated data with a known, simple structure. Real resignations have causes no HRIS records.</li>
          <li>Monthly snapshots: a decision made in the last week of a month shows up in the next snapshot.</li>
          <li>Scores are relative within the month scored: high means top 10% of that month, not a fixed probability.</li>
          <li>Retrain and re-audit when policy, pay structure or the workforce mix changes.</li>
        </ul>
      </Panel>
    </div>
  );
}
