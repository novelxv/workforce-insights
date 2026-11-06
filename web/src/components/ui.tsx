"use client";

import Link from "next/link";
import {
  useEffect,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

import { ErrorIcon, InfoIcon, WarningIcon } from "./icons";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANT: Record<Variant, string> = {
  primary: "bg-ink text-white hover:bg-ink-2 border border-ink",
  secondary: "bg-surface text-fg border border-line-strong hover:bg-surface-2",
  ghost: "text-fg-2 hover:bg-surface-3 border border-transparent",
  danger: "bg-surface text-critical border border-line-strong hover:bg-critical-soft",
};

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  return (
    <button
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-7 px-2.5 text-[13px]" : "h-9 px-3.5 text-sm",
        VARIANT[variant],
        className,
      )}
    />
  );
}

export function LinkButton({
  href,
  variant = "secondary",
  children,
  className,
  download,
}: {
  href: string;
  variant?: Variant;
  children: ReactNode;
  className?: string;
  download?: boolean;
}) {
  const cls = cx(
    "inline-flex h-9 items-center gap-1.5 rounded-md px-3.5 text-sm font-medium transition-colors",
    VARIANT[variant],
    className,
  );
  if (download || href.startsWith("/api/")) {
    return (
      <a href={href} className={cls} download={download}>
        {children}
      </a>
    );
  }
  return (
    <Link href={href} className={cls}>
      {children}
    </Link>
  );
}

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "ink" | "good" | "warning" | "critical" | "outline";
  className?: string;
}) {
  const tones = {
    neutral: "bg-surface-3 text-fg-2",
    ink: "bg-ink-soft text-ink",
    good: "bg-good-soft text-good",
    warning: "bg-warning-soft text-warning",
    critical: "bg-critical-soft text-critical",
    outline: "border border-line-strong text-fg-2",
  };
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-medium",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Panel({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx("rounded-lg border border-line bg-surface", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div>
            {title && <h2 className="text-[15px] font-semibold text-fg">{title}</h2>}
            {description && <p className="mt-0.5 text-[13px] text-fg-3">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-[13px] text-fg-3">{eyebrow}</div>}
        <h1 className="text-xl font-semibold tracking-tight text-fg">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-[13px] text-fg-2">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({
  label,
  value,
  sub,
  href,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  href?: string;
  tone?: "critical" | "warning";
}) {
  const body = (
    <>
      <div className="flex items-center gap-1.5 text-[13px] text-fg-2">
        {tone === "critical" && <ErrorIcon size={14} className="text-critical" />}
        {tone === "warning" && <WarningIcon size={14} className="text-warning" />}
        {label}
      </div>
      <div className="tabular mt-1 text-[26px] font-semibold leading-tight text-fg">{value}</div>
      {sub && <div className="mt-0.5 text-[12px] text-fg-3">{sub}</div>}
    </>
  );
  const cls = "block rounded-lg border border-line bg-surface px-4 py-3";
  return href ? (
    <Link href={href} className={cx(cls, "transition-colors hover:border-line-strong")}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

const control =
  "h-9 w-full rounded-md border border-line-strong bg-surface px-2.5 text-sm text-fg placeholder:text-fg-3 focus:border-series-1 disabled:bg-surface-3";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(control, props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(control, "pr-7", props.className)} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx(control, "h-auto py-2", props.className)} />;
}

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cx("block", className)}>
      <span className="mb-1 block text-[13px] font-medium text-fg-2">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[12px] text-fg-3">{hint}</span>}
    </label>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-critical/30 bg-critical-soft px-3 py-2 text-[13px] text-critical"
    >
      <ErrorIcon size={15} className="mt-0.5 shrink-0" />
      <div>{children}</div>
    </div>
  );
}

export function Note({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warning" }) {
  return (
    <div
      className={cx(
        "flex items-start gap-2 rounded-md px-3 py-2 text-[13px]",
        tone === "warning" ? "bg-warning-soft text-warning" : "bg-surface-3 text-fg-2",
      )}
    >
      {tone === "warning" ? (
        <WarningIcon size={15} className="mt-0.5 shrink-0" />
      ) : (
        <InfoIcon size={15} className="mt-0.5 shrink-0" />
      )}
      <div>{children}</div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded bg-surface-3", className)} />;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-4 py-10 text-center">
      <div className="text-sm font-medium text-fg">{title}</div>
      {children && <div className="mx-auto mt-1 max-w-md text-[13px] text-fg-3">{children}</div>}
    </div>
  );
}

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx("overflow-x-auto", className)}>
      <table className="w-full border-collapse text-left text-[13px]">{children}</table>
    </div>
  );
}

export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    <th
      className={cx(
        "sticky top-0 whitespace-nowrap border-b border-line bg-surface-2 px-3 py-2 text-[12px] font-medium text-fg-2",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({ children, className, colSpan }: { children?: ReactNode; className?: string; colSpan?: number }) {
  return (
    <td colSpan={colSpan} className={cx("border-b border-line px-3 py-2 align-top", className)}>
      {children}
    </td>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-2.5 text-[13px] text-fg-2">
      <span className="tabular">
        {from}–{to} of {total}
      </span>
      <div className="flex gap-1.5">
        <Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </Button>
        <Button size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next
        </Button>
      </div>
    </div>
  );
}

export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  width = "max-w-lg",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      className={cx("w-[calc(100%-2rem)] rounded-lg border border-line bg-surface p-0 text-fg shadow-xl", width)}
    >
      {open && (
        <div>
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 className="text-[15px] font-semibold">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              className="rounded px-1.5 text-lg leading-none text-fg-3 hover:bg-surface-3"
              aria-label="Close"
            >
              ×
            </button>
          </div>
          <div className="max-h-[70vh] overflow-y-auto px-4 py-4">{children}</div>
          {footer && (
            <div className="flex justify-end gap-2 border-t border-line bg-surface-2 px-4 py-3">{footer}</div>
          )}
        </div>
      )}
    </dialog>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { id: T; label: ReactNode; hidden?: boolean }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-line">
      {tabs
        .filter((t) => !t.hidden)
        .map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={value === t.id}
            onClick={() => onChange(t.id)}
            className={cx(
              "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-[13px] font-medium",
              value === t.id ? "border-ink text-ink" : "border-transparent text-fg-2 hover:text-fg",
            )}
          >
            {t.label}
          </button>
        ))}
    </div>
  );
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("font-mono text-[12.5px]", className)}>{children}</span>;
}
