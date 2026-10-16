import { Clock } from "lucide-react";

/** The intentional state for screens whose endpoints arrive in a later phase (the page still checks the API). */
export function ComingSoon({ phase, what, endpoint }: { phase: number; what: string; endpoint: string }) {
  return (
    <div className="mt-6 flex flex-col items-center gap-3 rounded-xl border border-dashed border-border px-6 py-16 text-center">
      <Clock className="size-7 text-muted-foreground" aria-hidden />
      <p className="font-medium">Arrives with phase {phase}</p>
      <p className="max-w-md text-sm text-muted-foreground">
        {what} The page calls <span className="font-mono text-foreground">{endpoint}</span> and shows it here as soon as the API serves it.
      </p>
    </div>
  );
}
