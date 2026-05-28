"use client";

import { PnlPoint, PnlRange } from "@/lib/api";

const RANGES: { key: PnlRange; label: string }[] = [
  { key: "hour", label: "1H" },
  { key: "day", label: "1D" },
  { key: "week", label: "1W" },
  { key: "month", label: "1M" },
];

const W = 600;
const H = 180;
const PAD = 10;

function signedUsd(v: number): string {
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${sign}$${Math.abs(v).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function PnlChart({
  points,
  range,
  onRange,
  loading = false,
  emptyHint,
}: {
  points: PnlPoint[];
  range: PnlRange;
  onRange: (r: PnlRange) => void;
  loading?: boolean;
  emptyHint?: string;
}) {
  const vals = points.map((p) => p.pnl);
  const last = vals.length ? vals[vals.length - 1] : 0;
  const positive = last >= 0;
  const stroke = positive ? "#34d399" : "#fb7185";
  const gradId = positive ? "pnl-up" : "pnl-down";

  let line = "";
  let area = "";
  let zeroY: number | null = null;
  if (points.length >= 2) {
    const min = Math.min(0, ...vals);
    const max = Math.max(0, ...vals);
    const span = max - min || 1;
    const xy = (i: number, v: number): [number, number] => [
      PAD + (i / (points.length - 1)) * (W - 2 * PAD),
      PAD + (1 - (v - min) / span) * (H - 2 * PAD),
    ];
    const pts = points.map((p, i) => xy(i, p.pnl));
    line = pts
      .map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`)
      .join(" ");
    const [x0] = pts[0];
    const [xN] = pts[pts.length - 1];
    area = `${line} L${xN.toFixed(1)},${(H - PAD).toFixed(1)} L${x0.toFixed(
      1
    )},${(H - PAD).toFixed(1)} Z`;
    zeroY = PAD + (1 - (0 - min) / span) * (H - 2 * PAD);
  }

  const hasChart = points.length >= 2;

  return (
    <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-5">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wider text-zinc-500">
            P&amp;L this period
          </div>
          <div
            className={`mt-0.5 text-2xl font-semibold tabular-nums ${
              positive ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {hasChart ? signedUsd(last) : "—"}
          </div>
        </div>
        <div className="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-950/60 p-1">
          {RANGES.map((r) => (
            <button
              key={r.key}
              onClick={() => onRange(r.key)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                range === r.key
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="relative mt-4 h-[180px]">
        {hasChart ? (
          <svg
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            className="h-full w-full"
          >
            <defs>
              <linearGradient id="pnl-up" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#34d399" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#34d399" stopOpacity="0" />
              </linearGradient>
              <linearGradient id="pnl-down" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#fb7185" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#fb7185" stopOpacity="0" />
              </linearGradient>
            </defs>
            {zeroY !== null && (
              <line
                x1={PAD}
                x2={W - PAD}
                y1={zeroY}
                y2={zeroY}
                stroke="#3f3f46"
                strokeWidth={1}
                strokeDasharray="4 4"
                vectorEffect="non-scaling-stroke"
              />
            )}
            <path d={area} fill={`url(#${gradId})`} />
            <path
              d={line}
              fill="none"
              stroke={stroke}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        ) : (
          <div className="flex h-full items-center justify-center text-center text-sm text-zinc-500">
            {loading
              ? "Loading…"
              : emptyHint || "Not enough history in this range yet."}
          </div>
        )}
      </div>
    </div>
  );
}
