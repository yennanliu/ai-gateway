import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, setAuthHeadersProvider } from "@/api/client";

function mockFetch(status: number, body: unknown, contentType = "application/json") {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => contentType },
    json: async () => body,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  setAuthHeadersProvider(() => ({}));
});

describe("api client", () => {
  it("parses JSON responses", async () => {
    vi.stubGlobal("fetch", mockFetch(200, { ok: true }));
    expect(await api("GET", "/x")).toEqual({ ok: true });
  });

  it("returns undefined for 204", async () => {
    vi.stubGlobal("fetch", mockFetch(204, ""));
    expect(await api("DELETE", "/x")).toBeUndefined();
  });

  it("throws ApiError on non-2xx with status", async () => {
    vi.stubGlobal("fetch", mockFetch(403, "forbidden", "text/plain"));
    await expect(api("GET", "/x")).rejects.toBeInstanceOf(ApiError);
    try {
      vi.stubGlobal("fetch", mockFetch(403, "forbidden", "text/plain"));
      await api("GET", "/x");
    } catch (e) {
      expect((e as ApiError).status).toBe(403);
    }
  });

  it("injects auth headers from the provider", async () => {
    const spy = mockFetch(200, {});
    vi.stubGlobal("fetch", spy);
    setAuthHeadersProvider(() => ({ "X-User-Id": "u1" }));
    await api("GET", "/x");
    expect(spy.mock.calls[0][1].headers["X-User-Id"]).toBe("u1");
  });
});
