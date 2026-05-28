"use client";

import { useState } from "react";

import { Me, SettingsUpdate, SizingMode, api } from "@/lib/api";

type NumKey =
  | "default_size_pct"
  | "max_slippage_bps"
  | "max_notional_per_trade_usd"
  | "daily_spend_cap_usd"
  | "max_open_exposure_usd"
  | "max_open_positions"
  | "min_price"
  | "max_price";

const NUM_FIELDS: { key: NumKey; label: string; hint: string; step: string; max?: number }[] = [
  { key: "default_size_pct", label: "Copy size ×", hint: "multiplier of leader size (1 = 1:1)", step: "0.1" },
  { key: "max_slippage_bps", label: "Max slippage (bps)", hint: "200 = 2%", step: "1" },
  { key: "max_notional_per_trade_usd", label: "Max $ / trade", hint: "0 = off", step: "1" },
  { key: "daily_spend_cap_usd", label: "Daily spend cap ($)", hint: "0 = off", step: "1" },
  { key: "max_open_exposure_usd", label: "Max open exposure ($)", hint: "0 = off", step: "1" },
  { key: "max_open_positions", label: "Max positions", hint: "0 = off", step: "1" },
  { key: "min_price", label: "Min price", hint: "skip buys below (0 = off)", step: "0.01", max: 1 },
  { key: "max_price", label: "Max price", hint: "skip buys above (1 = off)", step: "0.01", max: 1 },
];

export default function RiskPanel({
  token,
  me,
  onChange,
}: {
  token: string;
  me: Me;
  onChange: () => void;
}) {
  const [mode, setMode] = useState<SizingMode>(me.sizing_mode);
  const [vals, setVals] = useState<Record<NumKey, number>>(() => ({
    default_size_pct: me.default_size_pct,
    max_slippage_bps: me.max_slippage_bps,
    max_notional_per_trade_usd: me.max_notional_per_trade_usd,
    daily_spend_cap_usd: me.daily_spend_cap_usd,
    max_open_exposure_usd: me.max_open_exposure_usd,
    max_open_positions: me.max_open_positions,
    min_price: me.min_price,
    max_price: me.max_price,
  }));
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save() {
    setBusy(true);
    setSaved(false);
    const payload: SettingsUpdate = {
      sizing_mode: mode,
      default_size_pct: vals.default_size_pct,
      max_slippage_bps: Math.round(vals.max_slippage_bps),
      max_notional_per_trade_usd: vals.max_notional_per_trade_usd,
      daily_spend_cap_usd: vals.daily_spend_cap_usd,
      max_open_exposure_usd: vals.max_open_exposure_usd,
      max_open_positions: Math.round(vals.max_open_positions),
      min_price: vals.min_price,
      max_price: vals.max_price,
    };
    const ok = await api.updateSettings(token, payload);
    setBusy(false);
    if (ok) {
      setSaved(true);
      onChange();
      setTimeout(() => setSaved(false), 2500);
    }
  }

  return (
    <section className="mt-10">
      <h2 className="mb-3 text-sm uppercase tracking-wider text-zinc-400">Risk controls</h2>
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5">
        <div className="mb-5">
          <div className="text-xs uppercase tracking-wider text-zinc-500">Sizing mode</div>
          <div className="mt-2 inline-flex rounded-xl border border-zinc-800 bg-zinc-950/60 p-1">
            {(
              [
                { key: "multiplier", label: "Fixed multiplier" },
                { key: "proportional", label: "Proportional" },
              ] as { key: SizingMode; label: string }[]
            ).map((o) => (
              <button
                key={o.key}
                onClick={() => setMode(o.key)}
                className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
                  mode === o.key
                    ? "bg-zinc-800 text-zinc-100"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-zinc-500">
            {mode === "proportional"
              ? "Match the leader's % of portfolio against your own."
              : "Copy the leader's share count × the multiplier below."}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {NUM_FIELDS.map((f) => (
            <label key={f.key} className="block">
              <span className="text-xs uppercase tracking-wider text-zinc-500">{f.label}</span>
              <input
                type="number"
                min={0}
                max={f.max}
                step={f.step}
                value={vals[f.key]}
                onChange={(e) =>
                  setVals((v) => ({ ...v, [f.key]: parseFloat(e.target.value) || 0 }))
                }
                className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-sm tabular-nums outline-none focus:border-zinc-500"
              />
              <span className="mt-0.5 block text-[11px] text-zinc-600">{f.hint}</span>
            </label>
          ))}
        </div>

        <div className="mt-5 flex items-center gap-3">
          <button
            onClick={save}
            disabled={busy}
            className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Save changes"}
          </button>
          {saved && <span className="text-sm text-emerald-400">Saved ✓</span>}
        </div>
      </div>
    </section>
  );
}
