import { NextRequest, NextResponse } from "next/server";

function sessionMaxAge() {
  const value = Number(process.env.DASHBOARD_SESSION_MAX_AGE_SECONDS || 60 * 60 * 12);
  return Number.isFinite(value) && value > 0 ? value : 60 * 60 * 12;
}

export async function POST(request: NextRequest) {
  const { username, password } = await request.json();
  const expectedUser = process.env.DASHBOARD_USERNAME;
  const expectedPassword = process.env.DASHBOARD_PASSWORD;

  if (!expectedUser || !expectedPassword) {
    return NextResponse.json({ ok: true });
  }

  if (username !== expectedUser || password !== expectedPassword) {
    return NextResponse.json({ error: "Invalid username or password" }, { status: 401 });
  }

  const maxAge = sessionMaxAge();
  const expiresAt = Date.now() + maxAge * 1000;
  const response = NextResponse.json({ ok: true });
  response.cookies.set("dashboard_session", Buffer.from(`${expectedUser}:${expectedPassword}:${expiresAt}`).toString("base64"), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.DASHBOARD_COOKIE_SECURE === "true",
    path: "/",
    maxAge,
    // Set an explicit absolute expiry alongside maxAge so the cookie is
    // treated as persistent (survives browser restart) across all browsers.
    expires: new Date(expiresAt),
  });
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set("dashboard_session", "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.DASHBOARD_COOKIE_SECURE === "true",
    path: "/",
    maxAge: 0,
  });
  return response;
}
