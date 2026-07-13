export type Locale = "en" | "zh-TW";

export const LOCALES: { value: Locale; label: string }[] = [
  { value: "en", label: "English" },
  { value: "zh-TW", label: "繁體中文" },
];

/** BCP-47 tag written to <html lang> for each locale. */
export const HTML_LANG: Record<Locale, string> = {
  en: "en",
  "zh-TW": "zh-Hant",
};

/** Nested message tree. `en` is the source of truth; `zh-TW` mirrors its shape. */
export interface Messages {
  nav: { dashboard: string; models: string; teams: string; keys: string; usage: string; budgets: string };
  common: { totalCost: string; requests: string };
  app: { signOut: string; toLight: string; toDark: string; language: string };
  landing: {
    eyebrow: string;
    heroLine1: string;
    heroLine2: string;
    sub: string;
    signinTitle: string;
    userId: string;
    orgId: string;
    roles: string;
    enter: string;
    tipPre: string;
    tipPost: string;
    features: { title: string; body: string }[];
  };
  dashboard: { title: string; governanceApi: string; budgetAlerts: string };
  models: {
    title: string;
    publicName: string;
    provider: string;
    model: string;
    add: string;
    delete: string;
    empty: string;
    th: { name: string; provider: string; model: string; status: string };
  };
  teams: {
    title: string;
    name: string;
    create: string;
    empty: string;
    th: { name: string; id: string };
  };
  keys: {
    title: string;
    noTeamsPre: string;
    teamsLink: string;
    noTeamsPost: string;
    team: string;
    issue: string;
    newKey: string;
    revoke: string;
    empty: string;
    th: { prefix: string; status: string };
  };
  usage: {
    title: string;
    empty: string;
    th: { model: string; prompt: string; completion: string; cost: string; requests: string };
  };
  budgets: {
    title: string;
    scopeId: string;
    limit: string;
    set: string;
    overThreshold: string;
    empty: string;
    th: { scope: string; limit: string; spent: string; period: string };
  };
  health: { healthy: string; degraded: string; down: string };
}

const en: Messages = {
  nav: {
    dashboard: "Dashboard",
    models: "Models",
    teams: "Teams",
    keys: "Keys",
    usage: "Usage",
    budgets: "Budgets",
  },
  common: {
    totalCost: "Total cost",
    requests: "Requests",
  },
  app: {
    signOut: "Sign out",
    toLight: "Switch to light mode",
    toDark: "Switch to dark mode",
    language: "Language",
  },
  landing: {
    eyebrow: "Enterprise LLM gateway",
    heroLine1: "One API. Every model.",
    heroLine2: "Governed, metered, yours.",
    sub: "Self-hostable control plane on top of LiteLLM — keep your data in your boundary, govern access, and see every token and dollar.",
    signinTitle: "Dev sign-in (stand-in until OIDC)",
    userId: "user id",
    orgId: "org id",
    roles: "roles (comma)",
    enter: "Enter console",
    tipPre: "Tip: run",
    tipPost: "to get an org id and a ready virtual key.",
    features: [
      {
        title: "One API, every model",
        body: "An OpenAI-compatible endpoint in front of OpenAI, Anthropic, Gemini, Bedrock, and self-hosted models — with automatic routing and fallback.",
      },
      {
        title: "Virtual keys & governance",
        body: "Org → team → app hierarchy, RBAC, and scoped virtual keys. Bring your own provider keys; consumers never see them.",
      },
      {
        title: "Budgets & guardrails",
        body: "Per-scope budgets and rate limits, plus PII, prompt-injection, and schema guardrails enforced on every request.",
      },
      {
        title: "Usage & billing",
        body: "Every call metered and priced. Aggregate by model, team, or day; export invoices; alert before budgets blow.",
      },
    ],
  },
  dashboard: {
    title: "Dashboard",
    governanceApi: "Governance API",
    budgetAlerts: "Budget alerts",
  },
  models: {
    title: "Model registry",
    publicName: "public name",
    provider: "provider",
    model: "model",
    add: "Add model",
    delete: "Delete",
    empty: "No models yet.",
    th: { name: "Name", provider: "Provider", model: "Model", status: "Status" },
  },
  teams: {
    title: "Teams",
    name: "team name",
    create: "Create team",
    empty: "No teams yet — create one to issue keys.",
    th: { name: "Name", id: "Team ID" },
  },
  keys: {
    title: "Virtual keys",
    noTeamsPre: "No teams yet. Create one on the",
    teamsLink: "Teams",
    noTeamsPost: "page, then issue keys here.",
    team: "Team",
    issue: "Issue key",
    newKey: "New key (shown once):",
    revoke: "Revoke",
    empty: "No keys for this team yet.",
    th: { prefix: "Prefix", status: "Status" },
  },
  usage: {
    title: "Usage",
    empty: "No usage yet.",
    th: {
      model: "Model",
      prompt: "Prompt",
      completion: "Completion",
      cost: "Cost",
      requests: "Requests",
    },
  },
  budgets: {
    title: "Budgets",
    scopeId: "scope id",
    limit: "limit",
    set: "Set budget",
    overThreshold: "{n} budget(s) over threshold",
    empty: "No budgets set.",
    th: { scope: "Scope", limit: "Limit", spent: "Spent", period: "Period" },
  },
  health: { healthy: "Healthy", degraded: "Degraded", down: "Down" },
};

const zhTW: Messages = {
  nav: {
    dashboard: "儀表板",
    models: "模型",
    teams: "團隊",
    keys: "金鑰",
    usage: "用量",
    budgets: "預算",
  },
  common: {
    totalCost: "總花費",
    requests: "請求數",
  },
  app: {
    signOut: "登出",
    toLight: "切換至淺色模式",
    toDark: "切換至深色模式",
    language: "語言",
  },
  landing: {
    eyebrow: "企業級 LLM 閘道",
    heroLine1: "一個 API，串接所有模型。",
    heroLine2: "受治理、可計量、完全屬於你。",
    sub: "建構於 LiteLLM 之上、可自行部署的控制平面——讓資料留在你的邊界內、控管存取權限，並掌握每一個 token 與每一分錢。",
    signinTitle: "開發者登入（OIDC 上線前的暫用機制）",
    userId: "使用者 ID",
    orgId: "組織 ID",
    roles: "角色（以逗號分隔）",
    enter: "進入主控台",
    tipPre: "提示：執行",
    tipPost: "即可取得組織 ID 與一把可立即使用的虛擬金鑰。",
    features: [
      {
        title: "一個 API，涵蓋所有模型",
        body: "在 OpenAI、Anthropic、Gemini、Bedrock 與自建模型之前，提供相容於 OpenAI 的單一端點——具備自動路由與備援。",
      },
      {
        title: "虛擬金鑰與治理",
        body: "組織 → 團隊 → 應用程式的層級架構、RBAC 與範圍化虛擬金鑰。自帶供應商金鑰，使用者永遠看不到它們。",
      },
      {
        title: "預算與防護機制",
        body: "各範圍的預算與速率限制，並在每個請求上強制執行 PII、prompt injection 與 schema 防護。",
      },
      {
        title: "用量與計費",
        body: "每次呼叫皆計量並計價。可依模型、團隊或日期彙總、匯出帳單，並在預算爆表前發出警示。",
      },
    ],
  },
  dashboard: {
    title: "儀表板",
    governanceApi: "治理 API",
    budgetAlerts: "預算警示",
  },
  models: {
    title: "模型註冊表",
    publicName: "公開名稱",
    provider: "供應商",
    model: "模型",
    add: "新增模型",
    delete: "刪除",
    empty: "尚無模型。",
    th: { name: "名稱", provider: "供應商", model: "模型", status: "狀態" },
  },
  teams: {
    title: "團隊",
    name: "團隊名稱",
    create: "建立團隊",
    empty: "尚無團隊——建立一個以簽發金鑰。",
    th: { name: "名稱", id: "團隊 ID" },
  },
  keys: {
    title: "虛擬金鑰",
    noTeamsPre: "尚無團隊。請先至",
    teamsLink: "團隊",
    noTeamsPost: "頁面建立一個，再於此簽發金鑰。",
    team: "團隊",
    issue: "簽發金鑰",
    newKey: "新金鑰（僅顯示一次）：",
    revoke: "撤銷",
    empty: "此團隊尚無金鑰。",
    th: { prefix: "前綴", status: "狀態" },
  },
  usage: {
    title: "用量",
    empty: "尚無用量。",
    th: {
      model: "模型",
      prompt: "提示",
      completion: "完成",
      cost: "花費",
      requests: "請求數",
    },
  },
  budgets: {
    title: "預算",
    scopeId: "範圍 ID",
    limit: "上限",
    set: "設定預算",
    overThreshold: "{n} 筆預算已超過門檻",
    empty: "尚未設定預算。",
    th: { scope: "範圍", limit: "上限", spent: "已花費", period: "週期" },
  },
  health: { healthy: "正常", degraded: "降級", down: "中斷" },
};

export const messages: Record<Locale, Messages> = { en, "zh-TW": zhTW };
