import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { principalToHeaders } from "@/stores/auth";
import { useRegistryStore } from "@/stores/registry";
import { useKeysStore } from "@/stores/keys";
import { useUsageStore } from "@/stores/usage";

function mockFetch(body: unknown, status = 200, contentType = "application/json") {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => contentType },
    json: async () => body,
    text: async () => JSON.stringify(body),
  });
}

beforeEach(() => setActivePinia(createPinia()));
afterEach(() => vi.restoreAllMocks());

describe("auth headers", () => {
  it("maps a principal to dev headers", () => {
    expect(
      principalToHeaders({ userId: "u1", orgId: "o1", roles: ["org-admin", "auditor"] }),
    ).toEqual({ "X-User-Id": "u1", "X-Org-Id": "o1", "X-Org-Roles": "org-admin,auditor" });
  });

  it("returns empty headers when unauthenticated", () => {
    expect(principalToHeaders(null)).toEqual({});
  });
});

describe("registry store", () => {
  it("refresh loads models", async () => {
    vi.stubGlobal("fetch", mockFetch([{ id: "m1", public_name: "gpt" }]));
    const store = useRegistryStore();
    await store.refresh();
    expect(store.items).toHaveLength(1);
    expect(store.loading).toBe(false);
  });

  it("captures errors", async () => {
    vi.stubGlobal("fetch", mockFetch("boom", 500, "text/plain"));
    const store = useRegistryStore();
    await store.refresh();
    expect(store.error).toContain("boom");
  });
});

describe("keys store", () => {
  it("issue stores the one-time secret then refreshes", async () => {
    const fetchMock = vi
      .fn()
      // POST /keys -> issued
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: { get: () => "application/json" },
        json: async () => ({ id: "k1", prefix: "sk-ag-ab", key: "sk-ag-secret", status: "active" }),
      })
      // GET /keys -> list
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => "application/json" },
        json: async () => [{ id: "k1", prefix: "sk-ag-ab", status: "active" }],
      });
    vi.stubGlobal("fetch", fetchMock);
    const store = useKeysStore();
    const issued = await store.issue("t1");
    expect(issued.key).toBe("sk-ag-secret");
    expect(store.lastIssued?.key).toBe("sk-ag-secret");
    expect(store.items).toHaveLength(1);
  });
});

describe("usage store", () => {
  it("computes totals across rows", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch([
        { group: "gpt-4o", prompt_tokens: 10, completion_tokens: 0, cost: "2.0", requests: 2 },
        { group: "claude", prompt_tokens: 5, completion_tokens: 0, cost: "3.5", requests: 1 },
      ]),
    );
    const store = useUsageStore();
    await store.refresh();
    expect(store.totalCost).toBeCloseTo(5.5);
    expect(store.totalRequests).toBe(3);
  });
});
