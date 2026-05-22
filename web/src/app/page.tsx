async function getHealth() {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  try {
    const r = await fetch(`${base}/health`, { cache: "no-store" });
    if (!r.ok) return null;
    return (await r.json()) as { status: string; version: string };
  } catch {
    return null;
  }
}

export default async function Page() {
  const health = await getHealth();
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-4xl font-semibold tracking-tight">Polycopy</h1>
      <p className="mt-3 text-zinc-400">
        Copy-trade Polymarket from Telegram. Public dashboard coming online phase by phase.
      </p>

      <section className="mt-10 rounded-lg border border-zinc-800 bg-zinc-900/40 p-5">
        <h2 className="text-sm uppercase tracking-wider text-zinc-400">Backend status</h2>
        {health ? (
          <p className="mt-2">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-400 align-middle" />{" "}
            <span className="ml-2 font-mono">{health.status}</span>{" "}
            <span className="ml-3 text-zinc-500">v{health.version}</span>
          </p>
        ) : (
          <p className="mt-2 text-rose-400">offline</p>
        )}
      </section>

      <section className="mt-8 text-sm text-zinc-500">
        Phase 1 scaffold. Top traders, live copied-trade feed, and per-user P&amp;L land in later phases.
      </section>
    </main>
  );
}
