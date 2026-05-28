"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import PnlChart from "@/components/PnlChart";
import {
  AccountKind,
  CopiedTrade,
  Follow,
  Me,
  Pnl,
  PnlRange,
  PnlSeries,
  PaperPortfolio,
  api,
  pct,
  usd,
  profileUrl,
  marketUrl,
} from "@/lib/api";

const BOT_USERNAME = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME || "";
const TOKEN_KEY = "polycopy_token";

function statusColor(status: string) {
  if (status === "filled" || status === "submitted") return "text-emerald-400";
  if (status === "rejected") return "text-rose-400";
  return "text-zinc-500";
}

export default function Dashboard() {
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [pnl, setPnl] = useState<Pnl | null>(null);
  const [paper, setPaper] = useState<PaperPortfolio | null>(null);
  const [follows, setFollows] = useState<Follow[]>([]);
  const [trades, setTrades] = useState<CopiedTrade[]>([]);
  const [ready, setReady] = useState(false);

  const [account, setAccount] = useState<AccountKind>("paper");
  const [range, setRange] = useState<PnlRange>("day");
  const [series, setSeries] = useState<PnlSeries | null>(null);
  const [seriesLoading, setSeriesLoading] = useState(false);

  const loadAll = useCallback(async (tok: string) => {
    const m = await api.me(tok);
    if (!m) {
      localStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setReady(true);
      return;
    }
    setMe(m);
    setFollows((await api.myFollows(tok)) || []);
    setTrades((await api.myTrades(tok)) || []);
    setPnl(await api.myPnl(tok));
    setPaper(await api.myPaper(tok));
    setReady(true);
  }, []);

  useEffect(() => {
    let stored = localStorage.getItem(TOKEN_KEY);
    // Magic-link login: the bot's /login sends a link with #token=… in the
    // fragment. Adopt it, persist it, then strip it from the URL.
    if (window.location.hash.startsWith("#token=")) {
      const fromHash = decodeURIComponent(
        window.location.hash.slice("#token=".length)
      );
      if (fromHash) {
        localStorage.setItem(TOKEN_KEY, fromHash);
        stored = fromHash;
        history.replaceState(null, "", window.location.pathname);
      }
    }
    if (stored) {
      setToken(stored);
      loadAll(stored);
    } else {
      setReady(true);
    }
  }, [loadAll]);

  // Fetch the P&L series whenever the account or range changes.
  useEffect(() => {
    if (!token || !me) return;
    let active = true;
    setSeriesLoading(true);
    api.myPnlSeries(token, account, range).then((s) => {
      if (active) {
        setSeries(s);
        setSeriesLoading(false);
      }
    });
    return () => {
      active = false;
    };
  }, [token, me, account, range]);

  // Telegram login widget
  useEffect(() => {
    if (token || !BOT_USERNAME) return;
    (window as unknown as { onTelegramAuth: (u: Record<string, unknown>) => void }).onTelegramAuth =
      async (user) => {
        const res = await api.authTelegram(user);
        if (res) {
          localStorage.setItem(TOKEN_KEY, res.token);
          setToken(res.token);
          await loadAll(res.token);
        }
      };
    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", BOT_USERNAME);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-request-access", "write");
    document.getElementById("tg-login")?.appendChild(script);
  }, [token, loadAll]);

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setMe(null);
  }

  const isPaper = account === "paper";
  const value = isPaper ? paper?.portfolio_value ?? 0 : pnl?.portfolio_value ?? 0;
  const totalPnl = isPaper
    ? paper?.total_pnl ?? 0
    : (pnl?.realized_pnl ?? 0) + (pnl?.unrealized_pnl ?? 0);
  const winRate = isPaper ? paper?.win_rate ?? null : pnl?.win_rate ?? null;
  const settled = isPaper ? paper?.settled_markets ?? 0 : pnl?.settled_markets ?? 0;
  const openPos = isPaper ? paper?.open_positions ?? 0 : pnl?.open_positions ?? 0;

  return (
    <main className="mx-auto max-w-5xl px-6 pb-20">
      <header className="sticky top-0 z-10 -mx-6 mb-2 flex items-center justify-between border-b border-zinc-800/60 bg-zinc-950/80 px-6 py-4 backdrop-blur">
        <Link
          href="/"
          className="bg-gradient-to-r from-emerald-400 to-teal-300 bg-clip-text text-xl font-bold tracking-tight text-transparent"
        >
          Polycopy
        </Link>
        {me && (
          <div className="flex items-center gap-3">
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                me.paper_trading
                  ? "border border-amber-500/40 bg-amber-500/10 text-amber-400"
                  : "border border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
              }`}
            >
              {me.paper_trading ? "PAPER MODE" : "LIVE MODE"}
            </span>
            <button
              onClick={logout}
              className="text-sm text-zinc-400 transition hover:text-zinc-200"
            >
              Sign out
            </button>
          </div>
        )}
      </header>

      {!ready && <p className="mt-10 text-zinc-500">Loading…</p>}

      {ready && !me && (
        <section className="mt-24 text-center">
          <h2 className="text-2xl font-semibold">Sign in to see your copy-trading</h2>
          <p className="mx-auto mt-3 max-w-md text-sm text-zinc-400">
            Open the bot in Telegram and send{" "}
            <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-200">
              /login
            </code>
            . It replies with a private link that signs you in here — no browser
            extensions or pop-ups required.
          </p>
          {BOT_USERNAME && (
            <p className="mx-auto mt-6 max-w-md text-xs text-zinc-500">
              Prefer the Telegram button? It also works in browsers without
              strict privacy blockers:
            </p>
          )}
          <div id="tg-login" className="mt-3 flex justify-center" />
        </section>
      )}

      {ready && me && (
        <>
          {/* Hero: active account value + P&L, with the paper/live toggle. */}
          <section className="mt-8 rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/30 p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="text-xs uppercase tracking-wider text-zinc-500">
                  {isPaper ? "Paper portfolio" : "Live portfolio"}
                </div>
                <div className="mt-1 text-4xl font-bold tabular-nums">{usd(value)}</div>
                <div className="mt-1 text-sm">
                  <Pl value={totalPnl} /> <span className="text-zinc-500">all-time P&amp;L</span>
                </div>
              </div>
              <AccountToggle account={account} onChange={setAccount} linked={me.linked} />
            </div>

            <div className="mt-6">
              <PnlChart
                points={series?.account === account ? series.points : []}
                range={range}
                onRange={setRange}
                loading={seriesLoading}
                emptyHint={
                  isPaper
                    ? "No closed paper trades in this range yet."
                    : "Live P&L history is recorded hourly — it fills in over time."
                }
              />
            </div>
          </section>

          {/* Active-account stat cards. */}
          <section className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Card title="Portfolio value">{usd(value)}</Card>
            <Card title="Total P&L">
              <Pl value={totalPnl} />
            </Card>
            <Card title="Win rate">
              {pct(winRate)}
              <div className="text-xs text-zinc-500">{settled} settled</div>
            </Card>
            <Card title="Open positions">{openPos}</Card>
          </section>

          {isPaper ? (
            <PaperPanel token={token!} me={me} paper={paper} onChange={() => loadAll(token!)} />
          ) : (
            <section className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Card title="Wallet">
                {me.linked ? (
                  <span className="text-emerald-400">
                    {me.wallet_origin === "created" ? "custodial" : "linked"}
                  </span>
                ) : (
                  <span className="text-amber-400">none</span>
                )}
                {me.wallet_address && (
                  <div className="font-mono text-xs text-zinc-500">
                    {me.wallet_address.slice(0, 6)}…{me.wallet_address.slice(-4)}
                  </div>
                )}
              </Card>
              <Card title="Unrealized P&L">
                <Pl value={pnl?.unrealized_pnl ?? 0} />
              </Card>
              <Card title="Realized P&L">
                <Pl value={pnl?.realized_pnl ?? 0} />
              </Card>
              <Card title="Auto-copy">
                <span className={me.auto_scout_enabled ? "text-emerald-400" : "text-zinc-400"}>
                  {me.auto_scout_enabled ? "on" : "off"}
                </span>
              </Card>
            </section>
          )}

          <section className="mt-10">
            <h2 className="mb-3 text-sm uppercase tracking-wider text-zinc-400">
              Copying ({follows.length})
            </h2>
            {follows.length ? (
              <ul className="space-y-2">
                {follows.map((f) => (
                  <li
                    key={f.wallet}
                    className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-2.5 text-sm transition hover:border-zinc-700"
                  >
                    <a
                      href={profileUrl(f.wallet)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium hover:text-emerald-400 hover:underline"
                    >
                      {f.display_name || `${f.wallet.slice(0, 6)}…${f.wallet.slice(-4)}`}
                    </a>
                    <span className="flex items-center gap-4">
                      <span className="text-zinc-500">{f.source}</span>
                      <span className="text-emerald-400">{pct(f.win_rate)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-zinc-500">
                Not copying anyone yet. Use /follow in the bot.
              </p>
            )}
          </section>

          <section className="mt-10">
            <h2 className="mb-3 text-sm uppercase tracking-wider text-zinc-400">
              Recent copied trades
            </h2>
            {trades.length ? (
              <div className="overflow-hidden rounded-xl border border-zinc-800">
                <table className="w-full text-sm">
                  <thead className="bg-zinc-900/60 text-left text-xs uppercase tracking-wider text-zinc-400">
                    <tr>
                      <th className="px-4 py-3">Market</th>
                      <th className="px-4 py-3">Side</th>
                      <th className="px-4 py-3 text-right">Size</th>
                      <th className="px-4 py-3 text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {trades.map((t, i) => (
                      <tr key={i} className="transition hover:bg-zinc-900/40">
                        <td className="px-4 py-3 max-w-xs truncate">
                          {marketUrl(t.market_slug) ? (
                            <a
                              href={marketUrl(t.market_slug)!}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="hover:text-emerald-400 hover:underline"
                            >
                              {t.market_question || "—"}
                            </a>
                          ) : (
                            t.market_question || "—"
                          )}
                          <span className="ml-2 text-xs text-zinc-500">{t.outcome}</span>
                        </td>
                        <td className="px-4 py-3">{t.side}</td>
                        <td className="px-4 py-3 text-right text-zinc-400">
                          {t.our_size ?? "—"}
                        </td>
                        <td className={`px-4 py-3 text-right ${statusColor(t.status)}`}>
                          {t.status}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-zinc-500">No copied trades yet.</p>
            )}
          </section>
        </>
      )}
    </main>
  );
}

function AccountToggle({
  account,
  onChange,
  linked,
}: {
  account: AccountKind;
  onChange: (a: AccountKind) => void;
  linked: boolean;
}) {
  const opts: { key: AccountKind; label: string }[] = [
    { key: "paper", label: "Paper" },
    { key: "real", label: "Live" },
  ];
  return (
    <div className="inline-flex rounded-xl border border-zinc-800 bg-zinc-950/60 p-1">
      {opts.map((o) => {
        const activeTab = account === o.key;
        const liveDisabled = o.key === "real" && !linked;
        return (
          <button
            key={o.key}
            onClick={() => !liveDisabled && onChange(o.key)}
            disabled={liveDisabled}
            title={liveDisabled ? "Link a wallet to view your live account" : undefined}
            className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
              activeTab
                ? o.key === "paper"
                  ? "bg-amber-500/15 text-amber-300"
                  : "bg-emerald-500/15 text-emerald-300"
                : "text-zinc-500 hover:text-zinc-300"
            } ${liveDisabled ? "cursor-not-allowed opacity-40" : ""}`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function Pl({ value }: { value: number }) {
  const color = value > 0 ? "text-emerald-400" : value < 0 ? "text-rose-400" : "text-zinc-300";
  const sign = value > 0 ? "+" : "";
  return (
    <span className={`tabular-nums ${color}`}>
      {sign}
      {usd(value)}
    </span>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 transition hover:border-zinc-700">
      <div className="text-xs uppercase tracking-wider text-zinc-500">{title}</div>
      <div className="mt-1 font-medium">{children}</div>
    </div>
  );
}

function PaperPanel({
  token,
  me,
  paper,
  onChange,
}: {
  token: string;
  me: Me;
  paper: PaperPortfolio | null;
  onChange: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(payload: Parameters<typeof api.updateSettings>[1]) {
    setBusy(true);
    await api.updateSettings(token, payload);
    setBusy(false);
    onChange();
  }

  async function fund() {
    const value = parseFloat(amount.replace(/[$,]/g, ""));
    if (isNaN(value) || value < 0) return;
    await save({ paper_balance: value });
    setAmount("");
  }

  return (
    <section className="mt-6">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm uppercase tracking-wider text-zinc-400">Paper trading</h2>
        <button
          onClick={() => save({ paper_trading: !me.paper_trading })}
          disabled={busy}
          className={`rounded-full px-3 py-1 text-xs transition ${
            me.paper_trading
              ? "border border-amber-500/40 bg-amber-500/10 text-amber-400"
              : "border border-zinc-700 text-zinc-400 hover:text-zinc-200"
          } disabled:opacity-50`}
        >
          {me.paper_trading ? "ON — click to go live" : "OFF — click to simulate"}
        </button>
      </div>

      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="number"
            min="0"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="Imaginary balance, e.g. 1000"
            className="w-56 rounded-md border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm outline-none focus:border-zinc-500"
          />
          <button
            onClick={fund}
            disabled={busy || !amount}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:opacity-50"
          >
            {paper?.enabled ? "Reset balance" : "Set balance"}
          </button>
          <span className="text-xs text-zinc-500">
            Funds a fresh paper account and clears open paper positions.
          </span>
        </div>

        {paper?.enabled && (
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Card title="Cash">{usd(paper.cash)}</Card>
            <Card title="Invested">{usd(paper.market_value)}</Card>
            <Card title="Started with">{usd(paper.starting_balance)}</Card>
          </div>
        )}

        {paper?.enabled && paper.positions.length > 0 && (
          <div className="mt-4 overflow-hidden rounded-xl border border-zinc-800">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900/60 text-left text-xs uppercase tracking-wider text-zinc-400">
                <tr>
                  <th className="px-4 py-3">Market</th>
                  <th className="px-4 py-3 text-right">Shares</th>
                  <th className="px-4 py-3 text-right">Avg</th>
                  <th className="px-4 py-3 text-right">Now</th>
                  <th className="px-4 py-3 text-right">Value</th>
                  <th className="px-4 py-3 text-right">P&amp;L</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {paper.positions.map((p, i) => (
                  <tr key={i} className="transition hover:bg-zinc-900/40">
                    <td className="px-4 py-3 max-w-xs truncate">
                      {marketUrl(p.market_slug) ? (
                        <a
                          href={marketUrl(p.market_slug)!}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:text-emerald-400 hover:underline"
                        >
                          {p.market_question || "—"}
                        </a>
                      ) : (
                        p.market_question || "—"
                      )}
                      <span className="ml-2 text-xs text-zinc-500">{p.outcome}</span>
                    </td>
                    <td className="px-4 py-3 text-right text-zinc-400">{p.shares}</td>
                    <td className="px-4 py-3 text-right text-zinc-400">
                      {p.avg_price.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right text-zinc-400">
                      {p.cur_price.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right">{usd(p.value)}</td>
                    <td className="px-4 py-3 text-right">
                      <Pl value={p.unrealized_pnl} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
