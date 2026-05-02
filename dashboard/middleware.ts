import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const username = process.env.DASHBOARD_USERNAME;
  const password = process.env.DASHBOARD_PASSWORD;
  if (!username || !password) {
    return NextResponse.next();
  }

  const pathname = request.nextUrl.pathname;
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
    const response = NextResponse.redirect(new URL("/login", request.url));
    response.cookies.delete("dashboard_session");
    return response;
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
