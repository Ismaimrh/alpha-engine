/** Inline SVG sparkline — no chart lib for 20 tiny paths. */
export default function Sparkline({
  data,
  width = 96,
  height = 24,
}: {
  data: number[] | undefined;
  width?: number;
  height?: number;
}) {
  if (!data || data.length < 2) {
    return <div className="skeleton h-6 w-24" />;
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const step = width / (data.length - 1);
  const points = data
    .map((v, i) => `${(i * step).toFixed(1)},${(height - 2 - ((v - min) / span) * (height - 4)).toFixed(1)}`)
    .join(" ");
  const up = data[data.length - 1] >= data[0];
  return (
    <svg width={width} height={height} className="shrink-0" aria-hidden>
      <polyline
        points={points}
        fill="none"
        stroke={up ? "#2FBF71" : "#E5533C"}
        strokeWidth="1.25"
        strokeLinejoin="round"
      />
    </svg>
  );
}
