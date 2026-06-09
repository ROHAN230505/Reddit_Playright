import { NextRequest, NextResponse } from "next/server";

// Server-side proxy to the Instagram (doomscroller) service. The IG service is
// internal-only on the compose network (http://instagram:8000) and has no auth
// of its own, so the browser never talks to it directly — every call goes
// through this handler, which sits behind the dashboard's session middleware
// (only /api/login is whitelisted there). This keeps IG behind the dashboard
// login and avoids CORS, while letting the native Instagram section consume the
// IG service's clean /api/* JSON endpoints.

const IG_BASE =
  process.env.INSTAGRAM_API_BASE_URL ||
  process.env.INSTAGRAM_INTERNAL_URL ||
  "http://instagram:8000";

// Methods we forward. The IG service exposes GET/POST/PATCH/DELETE under /api/*.
async function proxy(request: NextRequest, segments: string[]) {
  const path = segments.map(encodeURIComponent).join("/");
  const search = request.nextUrl.search;
  const target = `${IG_BASE}/api/${path}${search}`;

  const init: RequestInit = {
    method: request.method,
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  };

  if (request.method !== "GET" && request.method !== "DELETE") {
    const body = await request.text();
    if (body) init.body = body;
  }

  try {
    const upstream = await fetch(target, init);
    const text = await upstream.text();
    // Pass through status + body. Force JSON content-type since all IG /api/*
    // routes return JSON (HTML partial routes are not proxied here).
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    return NextResponse.json(
      {
        error: "instagram_service_unreachable",
        detail: err instanceof Error ? err.message : String(err),
        target,
      },
      { status: 502 },
    );
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(request, path);
}

export async function POST(request: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(request, path);
}

export async function PATCH(request: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(request, path);
}

export async function DELETE(request: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(request, path);
}
