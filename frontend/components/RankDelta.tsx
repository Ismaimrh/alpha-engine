/** Rank movement vs prior day: ▲ climbed, ▼ fell, — flat/new. */
export default function RankDelta({ change }: { change: number | null }) {
  if (change === null) return <span className="font-mono text-2xs text-muted">—</span>;
  if (change === 0) return <span className="font-mono text-2xs text-muted">·</span>;
  const up = change > 0;
  return (
    <span
      className={`font-mono text-2xs tabular-nums ${up ? "text-gain" : "text-loss"}`}
      title={`${up ? "climbed" : "fell"} ${Math.abs(change)} places since prior session`}
    >
      {up ? "▲" : "▼"}{Math.abs(change)}
    </span>
  );
}
