import { NextResponse, type NextRequest } from "next/server";

// Optimistic check only: send people without a session cookie to the sign-in page.
// The API authorises every request on its own.
export function proxy(request: NextRequest) {
  if (request.cookies.has("insights_session")) return NextResponse.next();
  const url = new URL("/login", request.url);
  const next = request.nextUrl.pathname + request.nextUrl.search;
  if (next !== "/") url.searchParams.set("next", next);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!login|api|_next/static|_next/image|favicon.ico|icon.svg).*)"],
};
