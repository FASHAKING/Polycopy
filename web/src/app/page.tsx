import Link from "next/link";

import StatusBadge from "@/components/StatusBadge";
import TraderTable from "@/components/TraderTable";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <div className="text-2xl font-semibold">{value.toLocaleString()}</div>
      <div className="text-xs uppercase tracking-wider text-zinc-500">{label}</div>
    </div>
  );
}

export default async function Page() {
  const [stats, traders] = await Promise.all([api.stats(), api.topTraders(20)]);

  return (
    <main className="mx-auto max-w-4xl px-6 py-14">
      <header className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold tracking-tight">Polycopy</h1>
        <StatusBadge />
      </header>
      <p className="mt-3 max-w-2xl text-zinc-400">
        Copy-trade Polymarket from Telegram. Follow a specific trader by username, or let
        the scout auto-follow profitable traders sitting in a 60–80% win-rate band.
      </p>

      <div className="mt-6 flex gap-3">
        <Link
          href="/dashboard"
          className="rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-emerald-400"
        >
          Open dashboard
        </Link>
      </div>

      <section className="mt-10">
        <h2 className="mb-3 text-sm uppercase tracking-wider text-zinc-400">Bot activity</h2>
        {stats ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Users" value={stats.users} />
            <Stat label="Traders tracked" value={stats.traders_tracked} />
            <Stat label="Active follows" value={stats.active_follows} />
            <Stat label="Copied trades" value={stats.copied_trades} />
          </div>
        ) : (
          <p className="text-sm text-rose-400">Backend unreachable.</p>
        )}
      </section>

      <section className="mt-10">
        <h2 className="mb-3 text-sm uppercase tracking-wider text-zinc-400">
          Top scouted traders
        </h2>
        <TraderTable traders={traders || []} />
      </section>
    </main>
  );
}
