import type { Metadata } from "next";
import { Instrument_Serif, Inter, JetBrains_Mono } from "next/font/google";
import { Suspense } from "react";

import { TopBar } from "@/components/shell/top-bar";
import { Tour } from "@/components/shell/tour";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

import "./globals.css";

// Inter Variable for all UI; JetBrains Mono for ids and queries (a free stand-in for Berkeley Mono).
// The variable names stay --font-geist-* so globals.css and inline styles don't change.
const geistSans = Inter({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = JetBrains_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
// the landing's display serif, app-wide: page titles (globals.css h1) and the landing headlines
const display = Instrument_Serif({ variable: "--font-landing-serif", subsets: ["latin"], weight: "400", style: ["normal", "italic"] });

export const metadata: Metadata = {
  title: "Epicenter",
  description: "Find where every outage started: a live causal graph of your production system.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // the font variables go on <html>: Tailwind's base font-family resolves there, so on <body> they never applied
    <html lang="en" className={`dark ${geistSans.variable} ${geistMono.variable} ${display.variable}`}>
      <body className="min-h-screen font-sans antialiased">
        <TooltipProvider delayDuration={200}>
          {/* useSearchParams (env) needs a Suspense boundary for static rendering */}
          <Suspense>
            <TopBar />
            {children}
            <Tour />
          </Suspense>
          <Toaster position="bottom-right" />
        </TooltipProvider>
      </body>
    </html>
  );
}
