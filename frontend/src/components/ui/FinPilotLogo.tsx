interface Props {
  size?: number;
  className?: string;
}

export function FinPilotLogo({ size = 32, className }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="FinPilot AI"
    >
      <defs>
        <linearGradient id="fp-g" x1="0" y1="0" x2="100" y2="100" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#4f46e5" />
          <stop offset="100%" stopColor="#7c3aed" />
        </linearGradient>
      </defs>
      <rect width="100" height="100" rx="22" fill="url(#fp-g)" />
      <rect x="12" y="57" width="21" height="31" rx="5" fill="white" />
      <rect x="40" y="39" width="21" height="49" rx="5" fill="white" />
      <rect x="68" y="18" width="21" height="70" rx="5" fill="white" />
      <polyline
        points="22.5,57 50.5,39 78.5,18"
        stroke="white"
        strokeWidth="3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.45"
      />
      <circle cx="78.5" cy="18" r="5" fill="white" opacity="0.9" />
    </svg>
  );
}
