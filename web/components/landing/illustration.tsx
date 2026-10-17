import { existsSync } from "node:fs";
import path from "node:path";
import Image from "next/image";

import { cn } from "@/lib/utils";

/** True when the generated image `web/public/landing/<name>.webp` has been dropped in. */
export function hasArt(name: string): boolean {
  return existsSync(path.join(process.cwd(), "public", "landing", `${name}.webp`));
}

/**
 * An illustration slot: shows `public/landing/<name>.webp` when it exists, else `fallback` (or nothing). The box has a
 * fixed aspect ratio, so the image never shifts the layout. Server component: the check runs at render, no client JS.
 */
export function Illustration({ name, alt, ratio, className, fallback = null, priority = false }: {
  name: string;
  alt: string;
  ratio: string; // a Tailwind aspect class, e.g. "aspect-[21/9]"
  className?: string;
  fallback?: React.ReactNode;
  priority?: boolean;
}) {
  if (!hasArt(name)) return fallback;
  return (
    <div className={cn("relative overflow-hidden", ratio, className)}>
      <Image src={`/landing/${name}.webp`} alt={alt} fill sizes="(max-width: 768px) 100vw, 1200px" className="object-cover" priority={priority} />
    </div>
  );
}
