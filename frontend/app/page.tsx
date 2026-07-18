"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Clock3, Database, FileCheck2, FileText, PenLine } from "lucide-react";
import { api } from "./lib/api";
import { useProject } from "./components/ProjectContext";

type Run = { run_id: string; planned_title?: string | null; status: string; created_at: string; quality_report: { passed?: boolean } };
type DocumentPayload = { total_documents: number; total_chunks: number };

export default function Dashboard() {
  const { projectId } = useProject();
  const [runs, setRuns] = useState<Run[]>([]);
  const [documents, setDocuments] = useState<DocumentPayload>({ total_documents: 0, total_chunks: 0 });

  const load = useCallback(async () => {
    const [runItems, documentData] = await Promise.all([
      api<Run[]>(`/projects/${projectId}/generation-runs?limit=10`),
      api<DocumentPayload>(`/documents?project_id=${encodeURIComponent(projectId)}`),
    ]);
    setRuns(runItems); setDocuments(documentData);
  }, [projectId]);
  useEffect(() => { const timer = window.setTimeout(() => void load().catch(() => undefined), 0); return () => window.clearTimeout(timer); }, [load]);

  const metrics = useMemo(() => ({
    review: runs.filter((run) => run.status === "needs_review").length,
    approved: runs.filter((run) => ["approved", "published"].includes(run.status)).length,
    gate: runs.length ? Math.round(runs.filter((run) => run.quality_report?.passed).length / runs.length * 100) : 0,
  }), [runs]);

  return (
    <main className="mx-auto max-w-6xl px-5 py-7 lg:px-8">
      <header className="mb-7 flex items-start justify-between border-b border-slate-200 pb-5"><div><h1 className="text-2xl font-semibold">Tổng quan</h1><p className="mt-1 text-sm text-slate-500">{projectId}</p></div><Link href="/create" className="btn btn-primary"><PenLine size={16} /> Tạo bài</Link></header>
      <section className="mb-8 grid gap-px overflow-hidden rounded-md border border-slate-200 bg-slate-200 sm:grid-cols-2 lg:grid-cols-4">
        <Metric icon={<FileText size={18} />} label="Generation runs" value={runs.length} />
        <Metric icon={<Clock3 size={18} />} label="Chờ duyệt" value={metrics.review} />
        <Metric icon={<CheckCircle2 size={18} />} label="Đã duyệt" value={metrics.approved} />
        <Metric icon={<FileCheck2 size={18} />} label="Gate pass" value={`${metrics.gate}%`} />
      </section>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section><div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">Runs gần đây</h2><Link className="flex items-center gap-1 text-sm font-medium text-emerald-700" href="/review">Duyệt bài <ArrowRight size={15} /></Link></div><div className="overflow-hidden rounded-md border border-slate-200 bg-white">{runs.map((run) => <Link href={`/review?run=${run.run_id}`} key={run.run_id} className="flex items-center gap-4 border-b border-slate-100 px-4 py-4 last:border-0 hover:bg-slate-50"><div className={`h-2 w-2 rounded-full ${run.status === "published" ? "bg-emerald-500" : run.status === "needs_review" ? "bg-amber-500" : "bg-slate-300"}`} /><div className="min-w-0 flex-1"><div className="truncate text-sm font-medium">{run.planned_title || "Planning"}</div><div className="mt-1 text-xs text-slate-400">{run.run_id}</div></div><span className="text-xs text-slate-500">{run.status}</span></Link>)}{runs.length === 0 && <div className="px-4 py-14 text-center text-sm text-slate-400">Chưa có generation run</div>}</div></section>
        <aside><h2 className="mb-3 font-semibold">Knowledge index</h2><div className="rounded-md border border-slate-200 bg-white p-5"><Database className="mb-4 text-emerald-600" size={22} /><div className="text-3xl font-semibold">{documents.total_documents}</div><div className="mt-1 text-sm text-slate-500">documents · {documents.total_chunks} chunks</div><Link href="/rag" className="btn btn-secondary mt-5 w-full">Quản lý nguồn</Link></div></aside>
      </div>
    </main>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: number | string }) {
  return <div className="bg-white p-5"><div className="mb-4 text-slate-400">{icon}</div><div className="text-2xl font-semibold">{value}</div><div className="mt-1 text-xs font-medium uppercase text-slate-400">{label}</div></div>;
}
