import { afterEach, describe, expect, it, vi } from "vitest";
import { dataPlane } from "@/api/client";

afterEach(() => vi.restoreAllMocks());

function resp(status: number, body: unknown, contentType = "application/json") {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => contentType },
    json: async () => body,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  };
}

describe("dataPlane client", () => {
  it("fetches the compiled status via the API wrapper", async () => {
    const body = { litellm_version: "1.91.1", routing: {}, models: [], model_count: 0 };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(resp(200, body)));
    expect(await dataPlane.status()).toEqual(body);
  });

  it("strips surrounding quotes from the liveness message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(resp(200, "I'm alive!")));
    expect(await dataPlane.liveness()).toEqual({ ok: true, detail: "I'm alive!" });
  });

  it("never throws on a liveness network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")));
    expect(await dataPlane.liveness()).toEqual({ ok: false, detail: "boom" });
  });

  it("parses readiness status + db", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(resp(200, { status: "healthy", db: "Not connected" })));
    expect(await dataPlane.readiness()).toEqual({ ok: true, status: "healthy", db: "Not connected" });
  });

  it("posts a virtual-key completion with a Bearer header (not dev principal)", async () => {
    const spy = vi.fn().mockResolvedValue(resp(200, { id: "cmpl-1" }));
    vi.stubGlobal("fetch", spy);
    const out = await dataPlane.chat("sk-ag-abc", "gpt", "hi");
    expect(spy.mock.calls[0][0]).toBe("/v1/chat/completions");
    const init = spy.mock.calls[0][1];
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer sk-ag-abc");
    expect(JSON.parse(init.body)).toEqual({ model: "gpt", messages: [{ role: "user", content: "hi" }] });
    expect(out.ok).toBe(true);
  });
});
