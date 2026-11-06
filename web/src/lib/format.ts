import type { Unit } from "./types";

const number = new Intl.NumberFormat("en-US");
const oneDecimal = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const twoDecimals = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const monthFmt = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });
const monthShort = new Intl.DateTimeFormat("en-GB", { month: "short", year: "2-digit", timeZone: "UTC" });
const dateTime = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Asia/Jakarta",
});

export const fmtNumber = (v?: number | null) => (v === null || v === undefined ? "—" : number.format(v));

export function fmtValue(v: number | null | undefined, unit: Unit): string {
  if (v === null || v === undefined) return "—";
  switch (unit) {
    case "count":
      return number.format(Math.round(v));
    case "percent":
      return `${oneDecimal.format(v * 100)}%`;
    case "years":
      return `${oneDecimal.format(v)} yrs`;
    case "hours":
      return `${oneDecimal.format(v)} h`;
    case "ratio":
      return twoDecimals.format(v);
  }
}

/** Axis ticks: shorter than fmtValue, no unit words. */
export function fmtTick(v: number, unit: Unit): string {
  if (unit === "percent") return `${Math.round(v * 100)}%`;
  if (unit === "ratio") return twoDecimals.format(v);
  if (unit === "years" || unit === "hours") return oneDecimal.format(v);
  return number.format(v);
}

/** Difference between two values of the same metric. Percent metrics change in points. */
export function fmtChange(delta: number, unit: Unit): string {
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : "±";
  const abs = Math.abs(delta);
  switch (unit) {
    case "count":
      return `${sign}${number.format(Math.round(abs))}`;
    case "percent":
      return `${sign}${oneDecimal.format(abs * 100)} pts`;
    case "years":
      return `${sign}${oneDecimal.format(abs)} yrs`;
    case "hours":
      return `${sign}${oneDecimal.format(abs)} h`;
    case "ratio":
      return `${sign}${twoDecimals.format(abs)}`;
  }
}

function utc(iso: string): Date {
  return new Date(`${iso.slice(0, 10)}T00:00:00Z`);
}

export const fmtMonth = (iso?: string | null) => (iso ? monthFmt.format(utc(iso)) : "—");
export const fmtMonthShort = (iso: string) => monthShort.format(utc(iso));
export const fmtDateTime = (iso?: string | null) => (iso ? dateTime.format(new Date(iso)) : "—");

export function fmtTenure(months: number): string {
  if (months < 12) return `${months} mo`;
  const y = Math.floor(months / 12);
  const m = months % 12;
  return m ? `${y} y ${m} mo` : `${y} y`;
}

export const ROLE_LABEL: Record<string, string> = {
  HR_ADMIN: "HR analytics admin",
  HRBP: "HR business partner",
  LEADER: "Leader",
};
