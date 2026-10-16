/** Display helpers shared by every screen. */

export const pct = (x: number | null | undefined, digits = 0) =>
  x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`;

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 0) return "just now";
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  const d = new Date(iso);
  return s < 365 * 86400 ? d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) : d.getFullYear().toString();
}

/** `svc/GET /x` → `["svc", "GET /x"]`. */
export function splitOp(op: string): [string, string] {
  const i = op.indexOf("/");
  return i < 0 ? [op, ""] : [op.slice(0, i), op.slice(i + 1)];
}

/** A stable hue per service (FNV-1a), so the same service has the same colour on every screen. */
export function serviceHue(service: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < service.length; i++) h = Math.imul(h ^ service.charCodeAt(i), 0x01000193);
  return (h >>> 0) % 360;
}

export const serviceColor = (service: string, alpha = 1) => `oklch(0.72 0.09 ${serviceHue(service)} / ${alpha})` // quiet hues: colour is for status;

export const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  supported: "Supported",
  refuted: "Refuted",
  inconclusive: "Inconclusive",
  pruned: "Pruned",
  confirmed: "Root cause",
  diagnosing: "Diagnosing",
  diagnosed: "Diagnosed",
  no_root_cause: "No root cause",
  delivered: "Delivered",
  resolved: "Resolved",
};
