/**
 * Agent "portraits" for the landing's team grid: what each agent does to the graph, drawn as a small SVG scene.
 * Coloured (gold, cream, coral); the card shows them grayscale until hover, like the reference's headshots.
 */
const G = "#E6C77D"; // = --color-gold, --color-cream, --color-coral-red (SVG attributes take literal colours)
const C = "#DEDBC8";
const R = "#EB5757";

function Frame({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 120 160" className="h-full w-full" aria-hidden>
      <defs>
        <radialGradient id={`agent-bg-${id}`} cx="50%" cy="45%" r="70%">
          <stop offset="0%" stopColor="#1a1712" />
          <stop offset="100%" stopColor="#050505" />
        </radialGradient>
      </defs>
      <rect width="120" height="160" fill={`url(#agent-bg-${id})`} />
      {children}
    </svg>
  );
}

const dot = (x: number, y: number, r: number, fill: string, o = 1) => <circle cx={x} cy={y} r={r} fill={fill} opacity={o} />;

/** Triage: one alert fans out into every upstream suspect. */
export function TriageGlyph() {
  const ys = [40, 60, 80, 100, 120];
  return (
    <Frame id="triage">
      {ys.map((y) => <line key={y} x1="30" y1="80" x2="88" y2={y} stroke={G} strokeWidth="0.8" opacity="0.55" />)}
      {ys.map((y) => <g key={y}>{dot(88, y, 3.2, C, 0.8)}</g>)}
      {dot(30, 80, 6, G)}
      <circle cx="30" cy="80" r="12" fill="none" stroke={G} strokeWidth="0.6" opacity="0.4" />
      <circle cx="30" cy="80" r="19" fill="none" stroke={G} strokeWidth="0.4" opacity="0.2" />
    </Frame>
  );
}

/** Investigator: walks one path back to where it started. */
export function InvestigatorGlyph() {
  const pts: [number, number][] = [[22, 120], [44, 96], [66, 104], [84, 72], [98, 44]];
  return (
    <Frame id="investigator">
      {[[30, 60], [52, 52], [74, 132], [96, 110], [40, 140]].map(([x, y], i) => <g key={i}>{dot(x, y, 2.4, C, 0.35)}</g>)}
      <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke={G} strokeWidth="1.2" strokeDasharray="3 2" />
      {pts.map(([x, y], i) => <g key={i}>{dot(x, y, i === pts.length - 1 ? 5 : 3, i === pts.length - 1 ? G : C, i === pts.length - 1 ? 1 : 0.8)}</g>)}
      <circle cx="98" cy="44" r="13" fill="none" stroke={G} strokeWidth="1" />
      <line x1="107" y1="53" x2="114" y2="60" stroke={G} strokeWidth="1.6" strokeLinecap="round" />
    </Frame>
  );
}

/** Skeptic: challenges the winner; a suspect that doesn't explain the alert is struck out. */
export function SkepticGlyph() {
  return (
    <Frame id="skeptic">
      <line x1="34" y1="58" x2="86" y2="58" stroke={C} strokeWidth="0.8" opacity="0.4" />
      <line x1="34" y1="58" x2="60" y2="108" stroke={C} strokeWidth="0.8" opacity="0.4" />
      <line x1="86" y1="58" x2="60" y2="108" stroke={G} strokeWidth="1" opacity="0.7" />
      {dot(34, 58, 4, C, 0.7)}
      {dot(60, 108, 6, G)}
      {dot(86, 58, 6, R, 0.9)}
      <line x1="76" y1="48" x2="96" y2="68" stroke={R} strokeWidth="1.6" strokeLinecap="round" />
      <line x1="96" y1="48" x2="76" y2="68" stroke={R} strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="60" cy="108" r="13" fill="none" stroke={G} strokeWidth="0.6" opacity="0.5" />
    </Frame>
  );
}

/** Historian: the same signature, seen before, with the fix that worked. */
export function HistorianGlyph() {
  return (
    <Frame id="historian">
      {[44, 34, 24, 14].map((r, i) => (
        <circle key={r} cx="60" cy="80" r={r} fill="none" stroke={i === 3 ? G : C} strokeWidth={i === 3 ? 1 : 0.6} opacity={0.15 + i * 0.18} />
      ))}
      {dot(60, 80, 5, G)}
      {dot(96, 44, 3, C, 0.6)}
      {dot(24, 116, 3, C, 0.6)}
      <path d="M96 44 Q 80 60 66 76" fill="none" stroke={G} strokeWidth="0.8" strokeDasharray="2 2" opacity="0.7" />
      <path d="M24 116 Q 40 100 54 84" fill="none" stroke={G} strokeWidth="0.8" strokeDasharray="2 2" opacity="0.7" />
    </Frame>
  );
}
