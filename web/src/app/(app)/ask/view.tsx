"use client";

import { useState, type FormEvent } from "react";

import { ResultView } from "@/components/result";
import { Badge, Button, ErrorNote, Input, Note, PageHeader, Panel } from "@/components/ui";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/session";
import type { AskResponse } from "@/lib/types";

interface Answer extends AskResponse {
  id: number;
}

function Suggestions({ items, onPick }: { items: string[]; onPick: (q: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((q) => (
        <button
          key={q}
          type="button"
          onClick={() => onPick(q)}
          className="rounded-full border border-line-strong bg-surface px-2.5 py-1 text-[12.5px] text-fg-2 hover:border-ink hover:text-ink"
        >
          {q}
        </button>
      ))}
    </div>
  );
}

function AnswerCard({ answer, onPick }: { answer: Answer; onPick: (q: string) => void }) {
  return (
    <Panel
      title={answer.question}
      description={
        answer.status === "ok" && answer.result ? (
          <span>
            Interpreted as <span className="font-medium text-fg-2">{answer.result.description}</span>
          </span>
        ) : null
      }
      actions={<Badge tone="outline">{answer.parser === "gemini" ? "Parsed by Gemini" : "Parsed by rules"}</Badge>}
    >
      {answer.status === "ok" && answer.result && <ResultView result={answer.result} />}
      {answer.status === "unsupported" && (
        <div className="space-y-3">
          <Note>{answer.message}</Note>
          {answer.suggestions && answer.suggestions.length > 0 && (
            <div>
              <div className="mb-1.5 text-[12.5px] text-fg-3">Questions Ask can answer:</div>
              <Suggestions items={answer.suggestions} onPick={onPick} />
            </div>
          )}
        </div>
      )}
      {answer.status === "invalid" && (
        <div className="space-y-3">
          <ErrorNote>{answer.message}</ErrorNote>
          {answer.suggestions && answer.suggestions.length > 0 && (
            <div className="text-[12.5px] text-fg-3">Valid values: {answer.suggestions.join(", ")}</div>
          )}
        </div>
      )}
    </Panel>
  );
}

export function AskView() {
  const { meta } = useMeta();
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(q: string) {
    const text = q.trim();
    if (text.length < 3) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<AskResponse>("/ask", { question: text });
      setAnswers((prev) => [{ ...res, id: Date.now() }, ...prev].slice(0, 10));
      setQuestion("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Ask"
        description="Ask for a figure in plain English or simple Indonesian. The question is turned into a query over the defined metrics, checked, and run with the same rules as every other screen."
      />
      <div className="grid gap-5 lg:grid-cols-[1fr_300px]">
        <div className="min-w-0 space-y-4">
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              ask(question);
            }}
            className="flex gap-2"
          >
            <Input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. voluntary turnover by department this year"
              maxLength={300}
              aria-label="Question"
              className="h-10"
            />
            <Button type="submit" variant="primary" disabled={busy || question.trim().length < 3} className="h-10">
              {busy ? "Asking…" : "Ask"}
            </Button>
          </form>
          {meta && answers.length === 0 && (
            <div>
              <div className="mb-1.5 text-[12.5px] text-fg-3">Try one of these:</div>
              <Suggestions items={meta.examples} onPick={ask} />
            </div>
          )}
          <ErrorNote>{error}</ErrorNote>
          {answers.map((a) => (
            <AnswerCard key={a.id} answer={a} onPick={ask} />
          ))}
        </div>

        <aside className="space-y-4">
          <Panel title="How an answer is made">
            <ol className="list-decimal space-y-2 pl-4 text-[13px] text-fg-2">
              <li>
                The question becomes a <em>spec</em>: one metric, up to two breakdowns, filters and a period. Gemini does
                this when configured, constrained to the metric and value codes; otherwise a rules parser does.
              </li>
              <li>The spec is checked against the catalogue and your access. Nothing outside it can run.</li>
              <li>The server compiles the spec to parameterised SQL. No model writes SQL or sees employee records.</li>
              <li>Figures resting on fewer than {meta?.min_group_size ?? 5} people are withheld.</li>
            </ol>
          </Panel>
          <Panel title="What it will not do">
            <ul className="list-disc space-y-1.5 pl-4 text-[13px] text-fg-2">
              <li>Name or list individuals. Individual risk is on the Attrition risk page, for HR.</li>
              <li>Forecast. It reports what has happened.</li>
              <li>Explain why. It gives figures to break down further.</li>
            </ul>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
