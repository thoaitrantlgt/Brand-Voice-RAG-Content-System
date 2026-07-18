"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check, Loader2, RefreshCw, Send, X } from "lucide-react";
import { api } from "../lib/api";
import { useProject } from "../components/ProjectContext";

type RunSummary = { run_id: string; planned_title?: string | null; status: string; created_at: string; quality_report: { passed?: boolean } };
type RunDetail = RunSummary & {
  final_content?: string | null;
  edited_content?: string | null;
  human_score?: number | null;
  review_notes?: string | null;
  quality_report: { passed?: boolean; dimension_scores?: Record<string, number>; violations?: { code: string }[] };
  citations: { document_id: string; excerpt: string; relevance_score?: number }[];
  blog_id?: number | null;
};

export default function ReviewPage() {
  return <Suspense fallback={<div className="p-8"><Loader2 className="animate-spin" /></div>}><ReviewWorkspace /></Suspense>;
}

function ReviewWorkspace() {
  const params = useSearchParams();
  const { projectId } = useProject();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selected, setSelected] = useState<RunDetail | null>(null);
  const [content, setContent] = useState("");
  const [score, setScore] = useState(80);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const open = useCallback(async (runId: string) => {
    const detail = await api<RunDetail>(`/generation-runs/${runId}`);
    setSelected(detail);
    setContent(detail.edited_content || detail.final_content || "");
    setScore(detail.human_score ?? 80);
    setNotes(detail.review_notes ?? "");
  }, []);

  const load = useCallback(async () => {
    const items = await api<RunSummary[]>(`/projects/${projectId}/generation-runs`);
    setRuns(items);
    const requested = params.get("run");
    if (requested) await open(requested);
    else if (selected) await open(selected.run_id);
  }, [open, params, projectId, selected]);

  useEffect(() => {
    const timer = window.setTimeout(
      () => void load().catch((cause) => setError(cause.message)),
      0,
    );
    return () => window.clearTimeout(timer);
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const review = async (approved: boolean) => {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      const detail = await api<RunDetail>(`/generation-runs/${selected.run_id}/review`, {
        method: "POST",
        body: JSON.stringify({ approved, human_score: score, notes, edited_content: content }),
      });
      setSelected(detail);
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Review failed"); }
    finally { setBusy(false); }
  };

  const publish = async () => {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      const detail = await api<RunDetail>(`/generation-runs/${selected.run_id}/publish`, { method: "POST" });
      setSelected(detail); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Publish failed"); }
    finally { setBusy(false); }
  };

  return (
    <main className="min-h-screen">
      <header className="flex h-20 items-center justify-between border-b border-slate-200 bg-white px-6 lg:px-8">
        <div><h1 className="text-xl font-semibold">Duyệt bài</h1><p className="text-xs text-slate-500">{projectId}</p></div>
        <button className="btn btn-secondary" onClick={() => void load()} title="Refresh"><RefreshCw size={16} /></button>
      </header>
      {error && <div className="m-5 rounded-md bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      <div className="grid min-h-[calc(100vh-80px)] lg:grid-cols-[280px_minmax(0,1fr)_300px]">
        <aside className="border-r border-slate-200 bg-white p-3">
          <div className="mb-2 px-2 text-xs font-semibold uppercase text-slate-400">Generation runs</div>
          <div className="space-y-1">
            {runs.map((run) => <button key={run.run_id} onClick={() => void open(run.run_id)} className={`w-full rounded-md px-3 py-3 text-left ${selected?.run_id === run.run_id ? "bg-emerald-50 text-emerald-900" : "hover:bg-slate-50"}`}><div className="truncate text-sm font-medium">{run.planned_title || "Untitled"}</div><div className="mt-1 flex items-center justify-between text-[11px] text-slate-500"><span>{run.status}</span><span>{run.quality_report?.passed ? "gate pass" : "review"}</span></div></button>)}
          </div>
        </aside>

        <section className="p-5 lg:p-7">
          {!selected && <div className="flex h-full items-center justify-center text-sm text-slate-400">Chọn một generation run</div>}
          {selected && <><div className="mb-4 flex items-center justify-between"><div><h2 className="text-lg font-semibold">{selected.planned_title}</h2><p className="text-xs text-slate-500">{selected.status} · {selected.run_id}</p></div></div><textarea className="min-h-[680px] w-full resize-y rounded-md border border-slate-200 bg-white p-5 font-mono text-sm leading-7 outline-none focus:border-emerald-500" value={content} onChange={(event) => setContent(event.target.value)} /></>}
        </section>

        <aside className="border-l border-slate-200 bg-white p-5">
          {selected && <div className="space-y-6">
            <section><h3 className="mb-3 text-sm font-semibold">Quality</h3>{Object.entries(selected.quality_report.dimension_scores ?? {}).map(([key, value]) => <div key={key} className="mb-2 flex justify-between text-xs"><span className="text-slate-500">{key}</span><strong>{value}</strong></div>)}{(selected.quality_report.violations ?? []).map((item) => <div key={item.code} className="mb-1 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">{item.code}</div>)}</section>
            <section><h3 className="mb-3 text-sm font-semibold">Human review</h3><label className="text-xs text-slate-500">Score<input className="input mt-1" type="number" min={0} max={100} value={score} onChange={(event) => setScore(Number(event.target.value))} /></label><label className="mt-3 block text-xs text-slate-500">Notes<textarea className="input mt-1 min-h-24 resize-y" value={notes} onChange={(event) => setNotes(event.target.value)} /></label></section>
            <section><h3 className="mb-3 text-sm font-semibold">Sources</h3><div className="space-y-3">{selected.citations.map((item) => <div key={`${item.document_id}-${item.excerpt}`} className="text-xs"><strong>{item.document_id}</strong><p className="mt-1 line-clamp-3 text-slate-500">{item.excerpt}</p></div>)}</div></section>
            {selected.status === "needs_review" && <div className="grid grid-cols-2 gap-2"><button className="btn btn-secondary text-rose-700" disabled={busy} onClick={() => void review(false)}><X size={16} /> Reject</button><button className="btn btn-primary" disabled={busy} onClick={() => void review(true)}><Check size={16} /> Approve</button></div>}
            {selected.status === "approved" && <button className="btn btn-primary w-full" disabled={busy} onClick={() => void publish()}><Send size={16} /> Publish</button>}
            {selected.status === "published" && <div className="rounded-md bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-800">Published · Blog #{selected.blog_id}</div>}
          </div>}
        </aside>
      </div>
    </main>
  );
}
