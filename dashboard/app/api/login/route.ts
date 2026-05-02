import { NextRequest, NextResponse } from "next/server";

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

  const response = NextResponse.json({ ok: true });
  response.cookies.set("dashboard_session", Buffer.from(`${expectedUser}:${expectedPassword}`).toString("base64"), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.DASHBOARD_COOKIE_SECURE === "true",
    path: "/",
  });
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete("dashboard_session");
  return response;
}
