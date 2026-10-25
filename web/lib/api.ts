"use client";
import { useEffect, useState } from "react";
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public requestId: string = "",
  ) {
    super(message);
  }
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const csrf =
    document.cookie
      .split("; ")
      .find((c) => c.startsWith("neuralops_csrf="))
      ?.split("=")[1] ?? "";
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    cache: "no-store",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
      ...init.headers,
    },
  });
  const data = await response
    .json()
    .catch(() => ({ message: "The API returned an invalid response." }));
  if (!response.ok) {
    // A full navigation clears all scoped state after session loss.
    if (response.status === 401 && !path.startsWith("/auth/"))
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/login");
    throw new ApiError(
      response.status,
      data.message ?? "Request failed.",
      data.request_id,
    );
  }
  return data as T;
}
type ResourceState<T> = {
  path: string | null;
  data?: T;
  error?: Error;
  loading: boolean;
};
export function useResource<T>(path: string | null, refresh: number = 0) {
  const [state, setState] = useState<ResourceState<T>>({
    path,
    loading: Boolean(path),
  });
  useEffect(() => {
    if (!path) {
      setState((previous) =>
        previous.path === null ? previous : { path: null, loading: false },
      );
      return;
    }
    const controller = new AbortController();
    let active = true;
    async function load() {
      // Preserve loaded forms and keyboard focus during polling. Scope changes clear the view synchronously below.
      setState((previous) =>
        previous.path === path && previous.data !== undefined
          ? previous
          : { path, loading: true },
      );
      try {
        const data = await api<T>(path!, { signal: controller.signal });
        if (active) setState({ path, data, loading: false });
      } catch (error) {
        if (active && !controller.signal.aborted)
          setState((previous) => ({
            path,
            data: previous.path === path ? previous.data : undefined,
            error:
              error instanceof Error ? error : new Error("Request failed."),
            loading: false,
          }));
      }
    }
    void load();
    return () => {
      active = false;
      controller.abort();
    };
  }, [path, refresh]);
  return state.path === path
    ? state
    : ({ path, loading: Boolean(path) } as ResourceState<T>);
}
export const mutation = <T>(
  path: string,
  body?: unknown,
  method = "POST",
  idempotent = false,
) =>
  api<T>(path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: idempotent ? { "Idempotency-Key": crypto.randomUUID() } : {},
  });
// Reuse ICU formatters for the fraction precisions used by the UI.
const numberFormats = new Map<number, Intl.NumberFormat>();
function numberFormat(digits: number) {
  let format = numberFormats.get(digits);
  if (!format) {
    format = new Intl.NumberFormat("en-US", { maximumFractionDigits: digits });
    numberFormats.set(digits, format);
  }
  return format;
}
export const number = (value: number | null | undefined, digits = 0) =>
  value == null ? "—" : numberFormat(digits).format(value);
const dateFormat = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZoneName: "short",
});
export const date = (value: string) => {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "Invalid Date"
    : dateFormat.format(parsed);
};
