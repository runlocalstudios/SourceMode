import { NextRequest, NextResponse } from "next/server";
import { checkBasicAuth } from "./lib/auth";

// Gate EVERY route (including /api) behind HTTP Basic Auth.
// Excludes only Next internals; everything else — pages, API, favicon — is gated.
export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};

export function proxy(request: NextRequest) {
  const expectedUsername = process.env.PREVIEW_USERNAME || "preview";
  const expectedPassword = process.env.PREVIEW_PASSWORD;

  if (checkBasicAuth(request.headers.get("authorization"), expectedUsername, expectedPassword)) {
    return NextResponse.next();
  }

  return new NextResponse("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="SourceMode preview", charset="UTF-8"' },
  });
}
