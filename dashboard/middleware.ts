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

  const expectedToken = btoa(`${username}:${password}`);
  if (request.cookies.get("dashboard_session")?.value === expectedToken) {
    return NextResponse.next();
  }

  return NextResponse.redirect(new URL("/login", request.url));
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
