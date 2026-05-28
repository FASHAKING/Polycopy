export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Stats = {
  users: number;
  traders_tracked: number;
  active_follows: number;
  copied_trades: number;
  submitted: number;
  filled: number;
  skipped: number;
};

export type Trader = {
  wallet: string;
  display_name: string | null;
  win_rate: number | null;
  roi: number | null;
  trades_count: number;
  volume_usd: number;
  last_scored_at: string | null;
};

export type SizingMode = "multiplier" | "proportional";

export type Me = {
  telegram_id: number;
  telegram_username: string | null;
  email: string | null;
  auto_scout_enabled: boolean;
  notifications_enabled: boolean;
  paper_trading: boolean;
  paper_starting_balance: number;
  paper_balance: number;
  linked: boolean;
  wallet_origin: string | null;
  wallet_address: string | null;
  sizing_mode: SizingMode;
  default_size_pct: number;
  max_slippage_bps: number;
  max_notional_per_trade_usd: number;
  daily_spend_cap_usd: number;
  max_open_exposure_usd: number;
  max_open_positions: number;
  min_price: number;
  max_price: number;
};

export type SettingsUpdate = {
  paper_trading?: boolean;
  paper_balance?: number;
  auto_scout_enabled?: boolean;
  notifications_enabled?: boolean;
  sizing_mode?: SizingMode;
  default_size_pct?: number;
  max_slippage_bps?: number;
  max_notional_per_trade_usd?: number;
  daily_spend_cap_usd?: number;
  max_open_exposure_usd?: number;
  max_open_positions?: number;
  min_price?: number;
  max_price?: number;
};

export type PaperPosition = {
  token_id: string;
  market_question: string | null;
  market_slug: string | null;
  outcome: string;
  shares: number;
  avg_price: number;
  cur_price: number;
  value: number;
  unrealized_pnl: number;
};

export type PaperPortfolio = {
  enabled: boolean;
  starting_balance: number;
  cash: number;
  market_value: number;
  portfolio_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_pnl: number;
  open_positions: number;
  win_rate: number | null;
  settled_markets: number;
  positions: PaperPosition[];
};

export type Follow = {
  wallet: string;
  display_name: string | null;
  source: string;
  win_rate: number | null;
  created_at: string;
};

export type Pnl = {
  wallet_address: string | null;
  portfolio_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  win_rate: number | null;
  settled_markets: number;
  open_positions: number;
  trades_filled: number;
  trades_submitted: number;
  trades_skipped: number;
  trades_paper: number;
};

export type AccountKind = "paper" | "real";
export type PnlRange = "hour" | "day" | "week" | "month";

export type PnlPoint = { t: string; pnl: number };
export type PnlSeries = {
  account: AccountKind;
  range: PnlRange;
  points: PnlPoint[];
};

export type CopiedTrade = {
  market_question: string | null;
  market_slug: string | null;
  outcome: string;
  side: string;
  leader_price: number;
  leader_size: number;
  our_price: number | null;
  our_size: number | null;
  status: string;
  skip_reason: string | null;
  pnl_usd: number | null;
  created_at: string;
};

async function get<T>(path: string, token?: string): Promise<T | null> {
  try {
    const r = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

export const api = {
  health: () => get<{ status: string; version: string }>("/health"),
  stats: () => get<Stats>("/api/stats"),
  topTraders: (limit = 20) => get<Trader[]>(`/api/traders/top?limit=${limit}`),
  me: (token: string) => get<Me>("/api/me", token),
  myFollows: (token: string) => get<Follow[]>("/api/me/follows", token),
  myTrades: (token: string) => get<CopiedTrade[]>("/api/me/trades", token),
  myPnl: (token: string) => get<Pnl>("/api/me/pnl", token),
  myPnlSeries: (token: string, account: AccountKind, range: PnlRange) =>
    get<PnlSeries>(`/api/me/pnl/series?account=${account}&range=${range}`, token),
  myPaper: (token: string) => get<PaperPortfolio>("/api/me/paper", token),
  closePaper: async (token: string, tokenId: string, shares?: number) => {
    try {
      const r = await fetch(`${API_BASE}/api/me/paper/close`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ token_id: tokenId, shares }),
      });
      if (!r.ok) return null;
      return (await r.json()) as PaperPortfolio;
    } catch {
      return null;
    }
  },
  updateSettings: async (token: string, payload: SettingsUpdate) => {
    try {
      const r = await fetch(`${API_BASE}/api/me/settings`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      if (!r.ok) return null;
      return (await r.json()) as Me;
    } catch {
      return null;
    }
  },
  authTelegram: async (payload: Record<string, unknown>) => {
    const r = await fetch(`${API_BASE}/api/auth/telegram`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) return null;
    return (await r.json()) as { token: string; telegram_id: number };
  },
};

export const POLYMARKET_WEB = "https://polymarket.com";

export function profileUrl(wallet: string): string {
  return `${POLYMARKET_WEB}/profile/${wallet}`;
}

export function marketUrl(slug: string | null | undefined): string | null {
  return slug ? `${POLYMARKET_WEB}/event/${slug}` : null;
}

export function pct(x: number | null): string {
  return x === null ? "—" : `${(x * 100).toFixed(1)}%`;
}

export function usd(x: number): string {
  return x.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}
