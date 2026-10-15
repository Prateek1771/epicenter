import { HealthCard } from "@/components/health-card";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-4 py-16">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Epicenter</h1>
        <p className="text-muted-foreground">Find where every outage started.</p>
      </header>
      <HealthCard />
    </main>
  );
}
