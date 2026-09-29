export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`brand ${compact ? 'compact' : ''}`} aria-label="EasyDesign">
      <svg viewBox="0 0 40 40" aria-hidden="true">
        <rect x="1" y="1" width="38" height="38" rx="12" fill="currentColor" />
        <path
          d="M12 12h8M12 20h6M12 28h8M12 12v16M25 12c9 0 9 16 0 16"
          stroke="white"
          strokeWidth="2.2"
          fill="none"
          strokeLinecap="round"
        />
      </svg>
      {!compact && (
        <span>
          Easy<span className="brand-light">Design</span>
        </span>
      )}
    </span>
  );
}
