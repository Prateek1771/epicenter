import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";

import { TopBar } from "@/components/shell/top-bar";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Epicenter",
  description: "Find where every outage started: a live causal graph of your production system.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className={`${geistSans.variable} ${geistMono.variable} min-h-screen antialiased`}>
        <TooltipProvider delayDuration={200}>
          {/* useSearchParams (env) needs a Suspense boundary for static rendering */}
          <Suspense>
            <TopBar />
            {children}
          </Suspense>
          <Toaster position="bottom-right" />
        </TooltipProvider>
      </body>
    </html>
  );
}
