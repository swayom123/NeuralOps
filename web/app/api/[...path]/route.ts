import { type NextRequest } from "next/server";

// Fixed operator-configured upstream. No user-supplied destinations or forwarding credentials to arbitrary hosts.
async function forward(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  if (path[0] !== "v1" || path.some((part) => !/^[a-zA-Z0-9_.-]+$/.test(part)))
    return Response.json(
      { code: "NOT_FOUND", message: "API route not found." },
      { status: 404 },
    );
  const requestId = crypto.randomUUID();
  try {
    const upstream = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
    const destination = new URL(
      `/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`,
      upstream,
    );
    const headers = new Headers();
    for (const key of [
      "cookie",
      "origin",
      "content-type",
      "x-csrf-token",
      "idempotency-key",
    ]) {
      const value = request.headers.get(key);
      if (value) headers.set(key, value);
    }
    let body: Uint8Array | undefined;
    if (!["GET", "HEAD"].includes(request.method) && request.body) {
      const reader = request.body.getReader(),
        chunks: Uint8Array[] = [];
      let length = 0;
      let timedOut = false;
      const timer = setTimeout(() => {
        timedOut = true;
        void reader.cancel();
      }, 15000);
      try {
        for (let reads = 0; ; reads++) {
          const part = await reader.read();
          if (timedOut)
            return Response.json(
              {
                code: "REQUEST_TIMEOUT",
                message: "Request body deadline exceeded.",
                request_id: requestId,
              },
              { status: 408 },
            );
          if (part.done) break;
          length += part.value.byteLength;
          if (length > 1048576 || reads > 1024) {
            await reader.cancel();
            return Response.json(
              {
                code: "PAYLOAD_TOO_LARGE",
                message: "Request body exceeds allowed bounds.",
                request_id: requestId,
              },
              { status: 413 },
            );
          }
          chunks.push(part.value);
        }
      } finally {
        clearTimeout(timer);
      }
      body = new Uint8Array(length);
      let offset = 0;
      for (const chunk of chunks) {
        body.set(chunk, offset);
        offset += chunk.byteLength;
      }
    }
    const response = await fetch(destination, {
      method: request.method,
      headers,
      body: body as BodyInit | undefined,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(15000)]),
    });
    const output = new Headers({ "Cache-Control": "no-store" });
    for (const key of [
      "content-type",
      "location",
      "x-request-id",
      "content-disposition",
      "retry-after",
    ]) {
      const value = response.headers.get(key);
      if (value) output.set(key, value);
    }
    for (const cookie of response.headers.getSetCookie())
      output.append("Set-Cookie", cookie);
    return new Response(response.body, {
      status: response.status,
      headers: output,
    });
  } catch {
    return Response.json(
      {
        code: "UPSTREAM_UNAVAILABLE",
        message: "Control API unavailable. Retry later.",
        request_id: requestId,
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
export {
  forward as GET,
  forward as POST,
  forward as PATCH,
  forward as DELETE,
  forward as HEAD,
};
