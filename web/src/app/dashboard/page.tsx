"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  CopiedTrade,
  Follow,
  Me,
  api,
  pct,
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
  const [follows, setFollows] = useState<Follow[]>([]);
  const [trades, setTrades] = useState<CopiedTrade[]>([]);
  const [ready, setReady] = useState(false);

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
    setReady(true);
  }, []);

  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (stored) {
      setToken(stored);
      loadAll(stored);
    } else {
      setReady(true);
    }
  }, [loadAll]);

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

  return (
    <main className="mx-auto max-w-4xl px-6 py-14">
      <header className="flex items-center justify-between">
        <Link href="/" className="text-2xl font-semibold tracking-tight">
          Polycopy
        </Link>
        {me && (
          <button onClick={logout} className="text-sm text-zinc-400 hover:text-zinc-200">
            Sign out
          </button>
        )}
      </header>

      {!ready && <p className="mt-10 text-zinc-500">Loading…</p>}

      {ready && !me && (
        <section className="mt-16 text-center">
          <h2 className="text-xl font-medium">Sign in to see your copy-trading</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-zinc-400">
            Log in with the same Telegram account you use with the bot to view your
            followed traders, copied trades, and P&amp;L.
          </p>
          <div id="tg-login" className="mt-6 flex justify-center" />
          {!BOT_USERNAME && (
            <p className="mt-4 text-xs text-amber-400">
              Set NEXT_PUBLIC_TELEGRAM_BOT_USERNAME to enable Telegram login.
            </p>
          )}
        </section>
      )}

      {ready && me && (
        <>
          <section className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Card title="Account">
              {me.telegram_username ? `@${me.telegram_username}` : `#${me.telegram_id}`}
            </Card>
            <Card title="Polymarket">
              <span className={me.linked ? "text-emerald-400" : "text-amber-400"}>
                {me.linked ? "linked" : "not linked"}
              </span>
            </Card>
            <Card title="Auto-copy">
              <span className={me.auto_scout_enabled ? "text-emerald-400" : "text-zinc-400"}>
                {me.auto_scout_enabled ? "on" : "off"}
              </span>
            </Card>
          </section>

          <section className="mt-10">
            <h2 className="mb-3 text-sm uppercase tracking-wider text-zinc-400">
              Copying ({follows.length})
            </h2>
            {follows.length ? (
              <ul className="space-y-2">
                {follows.map((f) => (
                  <li
                    key={f.wallet}
                    className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-900/40 px-4 py-2 text-sm"
                  >
                    <span>{f.display_name || `${f.wallet.slice(0, 6)}…${f.wallet.slice(-4)}`}</span>
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
              <div className="overflow-hidden rounded-lg border border-zinc-800">
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
                      <tr key={i} className="hover:bg-zinc-900/30">
                        <td className="px-4 py-3 max-w-xs truncate">
                          {t.market_question || "—"}
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

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <div className="text-xs uppercase tracking-wider text-zinc-500">{title}</div>
      <div className="mt-1 font-medium">{children}</div>
    </div>
  );
}
