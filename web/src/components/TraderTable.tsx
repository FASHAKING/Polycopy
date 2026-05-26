import { Trader, pct, usd } from "@/lib/api";

function short(wallet: string) {
  return `${wallet.slice(0, 6)}…${wallet.slice(-4)}`;
}

export default function TraderTable({ traders }: { traders: Trader[] }) {
  if (!traders.length) {
    return (
      <p className="text-sm text-zinc-500">
        No scouted traders yet. The scout populates this once it runs.
      </p>
    );
  }
  return (
    <div className="overflow-hidden rounded-lg border border-zinc-800">
      <table className="w-full text-sm">
        <thead className="bg-zinc-900/60 text-left text-xs uppercase tracking-wider text-zinc-400">
          <tr>
            <th className="px-4 py-3">Trader</th>
            <th className="px-4 py-3 text-right">Win rate</th>
            <th className="px-4 py-3 text-right">ROI</th>
            <th className="px-4 py-3 text-right">Settled</th>
            <th className="px-4 py-3 text-right">Volume</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800">
          {traders.map((t) => (
            <tr key={t.wallet} className="hover:bg-zinc-900/30">
              <td className="px-4 py-3">
                <span className="font-medium">{t.display_name || short(t.wallet)}</span>
                {t.display_name && (
                  <span className="ml-2 font-mono text-xs text-zinc-500">{short(t.wallet)}</span>
                )}
              </td>
              <td className="px-4 py-3 text-right font-medium text-emerald-400">
                {pct(t.win_rate)}
              </td>
              <td className="px-4 py-3 text-right">
                {t.roi === null ? "—" : `${(t.roi * 100).toFixed(0)}%`}
              </td>
              <td className="px-4 py-3 text-right text-zinc-400">{t.trades_count}</td>
              <td className="px-4 py-3 text-right text-zinc-400">{usd(t.volume_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
