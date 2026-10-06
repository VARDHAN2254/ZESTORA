export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8 text-center">
      <div className="max-w-2xl space-y-6">
        <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-sm text-emerald-400">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          Phase 0: Project Skeleton
        </div>
        <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl text-white">
          ZESTORA
        </h1>
        <p className="text-lg text-slate-400">
          Production-grade food delivery platform foundation. Next.js frontend scaffolded and ready for local development.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-4 text-xs font-mono text-slate-400">
          <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">Customer</div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">Restaurant</div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">Delivery</div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">Admin</div>
        </div>
      </div>
    </main>
  );
}
