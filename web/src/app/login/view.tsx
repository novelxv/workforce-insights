"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import useSWR from "swr";

import { Button, ErrorNote, Field, Input } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";

interface DemoAccounts {
  password: string | null;
  accounts: { email: string; role: string; scope: string }[];
}

export function LoginView() {
  const router = useRouter();
  const next = useSearchParams().get("next") || "/";
  const { data: demo } = useSWR<DemoAccounts>("/auth/demo-accounts", fetcher);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function signIn(e: string, p: string) {
    setBusy(e);
    setError(null);
    try {
      await api.post("/auth/login", { email: e, password: p });
      router.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
      setBusy(null);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_520px]">
      <section className="hidden flex-col justify-between bg-ink px-12 py-10 text-white lg:flex">
        <div className="text-[15px] font-semibold">Arunika Workforce Insights</div>
        <div className="max-w-xl">
          <h1 className="text-[28px] font-semibold leading-tight">
            One definition of turnover, whether you read it on a chart, ask for it in a sentence or open it in Excel.
          </h1>
          <ul className="mt-6 space-y-3 text-[14px] text-white/80">
            <li>Fifteen HR metrics defined once and compiled to parameterised SQL over a star schema.</li>
            <li>
              Ask in plain English or simple Indonesian. The question becomes a checked query spec; no model writes
              SQL or sees a single employee record.
            </li>
            <li>Figures resting on fewer than five people are withheld, everywhere.</li>
            <li>Attrition risk for the next six months, with the reasons behind each score, for HR only.</li>
            <li>Monthly report as an Excel workbook with live formulas; a pseudonymous extract with DAX measures for Power BI.</li>
          </ul>
        </div>
        <p className="text-[12px] text-white/60">
          Arunika Life is a fictional life insurer. Every person and number here comes from a simulation.
        </p>
      </section>

      <section className="flex flex-col justify-center px-6 py-10 sm:px-10">
        <div className="mx-auto w-full max-w-sm">
          <h2 className="text-lg font-semibold">Sign in</h2>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              signIn(email.trim(), password);
            }}
            className="mt-4 space-y-3"
          >
            <Field label="Work email">
              <Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </Field>
            <Field label="Password">
              <Input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>
            <ErrorNote>{error}</ErrorNote>
            <Button type="submit" variant="primary" className="w-full" disabled={!!busy}>
              {busy === email.trim() ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          {demo && demo.accounts.length > 0 && (
            <div className="mt-8">
              <div className="flex items-baseline justify-between">
                <h3 className="text-[13px] font-semibold">Demo accounts</h3>
                {demo.password && (
                  <span className="text-[12px] text-fg-3">
                    password <code className="font-mono text-fg-2">{demo.password}</code>
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-[12.5px] text-fg-3">The same data, three levels of access.</p>
              <div className="mt-3 space-y-2">
                {demo.accounts.map((a) => (
                  <button
                    key={a.email}
                    type="button"
                    disabled={!!busy || !demo.password}
                    onClick={() => signIn(a.email, demo.password!)}
                    className="w-full rounded-md border border-line bg-surface px-3 py-2.5 text-left transition-colors hover:border-line-strong hover:bg-surface-2 disabled:opacity-60"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[13px] font-medium">{ROLE_LABEL[a.role] ?? a.role}</span>
                      <span className="text-[12px] text-fg-3">{busy === a.email ? "Signing in…" : a.email}</span>
                    </div>
                    <div className="mt-0.5 text-[12.5px] text-fg-2">{a.scope}</div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
