/** The WebbPulse mark: a flat line with a single beat. */
export function PulseMark({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 48 24"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M1 13h13l4-9 6 17 5-12 3 4h15"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** A wide pulse line that draws itself under the hero copy. */
export function HeroPulse({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 560 64"
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M2 36h300l14-28 22 52 18-40 11 16h191"
        pathLength={1}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
