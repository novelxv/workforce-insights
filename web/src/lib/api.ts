export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function messageFrom(body: unknown, status: number): string {
  if (body && typeof body === "object" && "issues" in body && Array.isArray((body as { issues: unknown }).issues)) {
    const issues = (body as { issues: { path: string; message: string }[] }).issues;
    return issues.map((i) => (i.path ? `${i.path}: ${i.message}` : i.message)).join("; ");
  }
  if (body && typeof body === "object" && "error" in body && typeof (body as { error: unknown }).error === "string") {
    return (body as { error: string }).error;
  }
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String((detail as { message: unknown }).message);
    }
    if (Array.isArray(detail)) {
      // FastAPI validation errors: [{loc, msg}, ...]
      return detail
        .map((d) => {
          const loc = Array.isArray(d.loc) ? d.loc.filter((p: unknown) => p !== "body").join(".") : "";
          const msg = String(d.msg ?? "").replace(/^Value error, /, "");
          return loc ? `${loc}: ${msg}` : msg;
        })
        .join("; ");
    }
  }
  return status === 401 ? "Your session has ended. Sign in again." : `Request failed (${status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { "content-type": "application/json", ...init?.headers },
  });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
    // A full reload on purpose: it drops every cached response from the old session.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const body = text ? JSON.parse(text) : undefined;
  if (!res.ok) throw new ApiError(res.status, messageFrom(body, res.status));
  return body as T;
}

export const fetcher = <T>(path: string) => request<T>(path);

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
    }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "" && v !== false) s.set(k, String(v));
  }
  const out = s.toString();
  return out ? `?${out}` : "";
}
