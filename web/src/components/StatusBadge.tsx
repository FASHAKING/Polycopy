import { api } from "@/lib/api";

export default async function StatusBadge() {
  const health = await api.health();
  return health ? (
    <span className="inline-flex items-center gap-2 text-sm">
      <span className="h-2 w-2 rounded-full bg-emerald-400" />
      <span className="text-zinc-400">online · v{health.version}</span>
    </span>
  ) : (
    <span className="inline-flex items-center gap-2 text-sm">
      <span className="h-2 w-2 rounded-full bg-rose-500" />
      <span className="text-rose-400">offline</span>
    </span>
  );
}
