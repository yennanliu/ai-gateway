export interface ModelDeployment {
  id: string;
  org_id: string;
  public_name: string;
  provider: string;
  model: string;
  api_base: string | null;
  credential_id: string | null;
  routing_tags: string[];
  tpm_limit: number | null;
  rpm_limit: number | null;
  status: string;
}

export interface VirtualKey {
  id: string;
  prefix: string;
  team_id: string;
  app_id: string | null;
  allowed_models: string[];
  status: string;
  created_at: string;
}

export interface KeyIssued extends VirtualKey {
  key: string;
}

export interface UsageRow {
  group: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  cost: string;
  requests: number;
}

export interface Budget {
  id: string;
  scope_type: string;
  scope_id: string;
  period: string;
  limit: string;
  soft_pct: number;
  hard_pct: number;
  spent: string;
}

export interface BudgetAlert {
  scope_type: string;
  scope_id: string;
  limit: string;
  spent: string;
  soft_exceeded: boolean;
  hard_exceeded: boolean;
}
