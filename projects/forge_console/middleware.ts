import { NextRequest, NextResponse } from "next/server";

function resolveToken(request: NextRequest): string {
  const direct = request.headers.get("x-forge-token");
  if (direct) {
    return direct;
  }
  const auth = request.headers.get("authorization") || "";
  if (auth.toLowerCase().startsWith("bearer ")) {
    return auth.slice(7).trim();
  }
  return "";
}

export function middleware(request: NextRequest) {
  const expected = process.env.FORGE_CONSOLE_TOKEN || "";
  if (!expected) {
    return NextResponse.json(
      { status: "error", message: "FORGE_CONSOLE_TOKEN is not configured." },
      { status: 503 },
    );
  }
  const provided = resolveToken(request);
  if (provided !== expected) {
    return NextResponse.json(
      { status: "error", message: "Unauthorized." },
      { status: 401 },
    );
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/api/forge/:path*"],
};
