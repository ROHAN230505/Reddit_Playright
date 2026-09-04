import { NextRequest, NextResponse } from "next/server";

const LEGACY_ROUTE_REDIRECTS: Record<string, string> = {
  "/feed": "/analytics?tab=feed",
  "/logs": "/analytics?tab=logs",
  "/live": "/replies?tab=realtime",
  "/accounts": "/settings?tab=accounts",
  "/proxies": "/settings?tab=proxies",
  "/subreddits": "/settings?tab=subreddits",
  "/replies/live": "/replies?tab=queue",
};

export function middleware(request: NextRequest) {
  const username = process.env.DASHBOARD_USERNAME;
  const password = process.env.DASHBOARD_PASSWORD;
  if (!username || !password) {
    return NextResponse.next();
  }

  const pathname = request.nextUrl.pathname;
  const legacyTarget = LEGACY_ROUTE_REDIRECTS[pathname];
  if (legacyTarget) {
    return NextResponse.redirect(new URL(legacyTarget, request.url));
  }

  if (pathname === "/login" || pathname.startsWith("/api/login")) {
    return NextResponse.next();
  }

  const token = request.cookies.get("dashboard_session")?.value;
  if (token) {
    try {
      const [tokenUser, tokenPassword, expiresAt] = atob(token).split(":");
      const expiresAtMs = Number(expiresAt);
      if (
        tokenUser === username &&
        tokenPassword === password &&
        Number.isFinite(expiresAtMs) &&
        expiresAtMs > Date.now()
      ) {
        return NextResponse.next();
      }
    } catch {
      // Invalid session cookies fall through to the login redirect.
    }
  }

  if (pathname !== "/login") {
    // Redirect unauthenticated requests to login. Do NOT delete the cookie
    // here: a transient/prefetch request without the cookie would otherwise
    // wipe an otherwise-valid session and force a re-login. Expired/invalid
    // cookies are simply overwritten on the next successful login.
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
