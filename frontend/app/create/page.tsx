"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, CheckCircle2, FileCheck2, Loader2, PenLine, Search, Wand2 } from "lucide-react";
import { api, Job, waitForJob } from "../lib/api";
import { useProject } from "../components/ProjectContext";
import { FinalEvaluation, FinalEvaluationPanel, HighlightedBlog } from "../components/FinalEvaluation";

type Run = {
  run_id: string;
  status: string;
  planned_title?: string | null;
  outline: string[];
  final_content?: string | null;
  quality_report: {
    passed?: boolean;
    dimension_scores?: Record<string, number>;
    violations?: { code: string; actual?: number; threshold?: number }[];
    final_evaluation?: FinalEvaluation;
  };
  citations: { document_id: string; source_url?: string | null; excerpt: string; relevance_score?: number }[];
  rewrite_count: number;
};

const initialBrief = {
  topic: "",
  keywords: "",
  audience: "",
  objective: "",
  category: "",
  mustCover: "",
  mustAvoid: "",
  targetLength: 800,
};

export default function CreatePage() {
  const { projectId } = useProject();
  const [brief, setBrief] = useState(initialBrief);
  const [run, setRun] = useState<Run | null>(null);
  const [outlineText, setOutlineText] = useState("");
  const [stage, setStage] = useState<"brief" | "planning" | "outline" | "generating" | "result">("brief");
  const [error, setError] = useState("");

  const list = (value: string) => value.split(/[,\n]/).map((item) => item.trim()).filter(Boolean);

  const createPlan = async () => {
    setError("");
    setStage("planning");
    try {
      const created = await api<{ run_id: string; job: Job }>(`/projects/${projectId}/generation-runs`, {
        method: "POST",
        body: JSON.stringify({
          topic: brief.topic,
          keywords: list(brief.keywords),
          audience: brief.audience,
          objective: brief.objective,
          category: brief.category || null,
          must_cover: list(brief.mustCover),
          must_avoid: list(brief.mustAvoid),
          target_length: brief.targetLength,
        }),
      });
      await waitForJob(created.job.job_id);
      const next = await api<Run>(`/generation-runs/${created.run_id}`);
      setRun(next);
      setOutlineText(next.outline.join("\n"));
      setStage("outline");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không thể tạo outline");
      setStage("brief");
    }
  };

  const generate = async () => {
    if (!run) return;
    setError("");
    setStage("generating");
    try {
      await api(`/generation-runs/${run.run_id}/outline`, {
        method: "PATCH",
        body: JSON.stringify({ outline: outlineText.split("\n").map((item) => item.trim()).filter(Boolean) }),
      });
      const queued = await api<{ job: Job }>(`/generation-runs/${run.run_id}/generate`, { method: "POST" });
      await waitForJob(queued.job.job_id);
      const completed = await api<Run>(`/generation-runs/${run.run_id}`);
      setRun(completed);
      setStage("result");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không thể tạo bài");
      setStage("outline");
    }
  };

  const reset = () => {
    setRun(null);
    setBrief(initialBrief);
    setOutlineText("");
    setError("");
    setStage("brief");
  };

  return (
    <main className="mx-auto w-full max-w-6xl px-5 py-7 lg:px-8">
      <header className="mb-7 flex items-start justify-between gap-4 border-b border-slate-200 pb-5">
        <div><h1 className="text-2xl font-semibold">Tạo bài viết</h1><p className="mt-1 text-sm text-slate-500">Project: {projectId}</p></div>
        {stage !== "brief" && <button className="btn btn-secondary" onClick={reset}><ArrowLeft size={16} /> Bài mới</button>}
      </header>

      {error && <div className="mb-5 flex items-center gap-2 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"><AlertCircle size={17} />{error}</div>}

      {stage === "brief" && (
        <section className="max-w-3xl space-y-5">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Chủ đề" value={brief.topic} onChange={(value) => setBrief({ ...brief, topic: value })} />
            <Field label="Từ khóa" value={brief.keywords} onChange={(value) => setBrief({ ...brief, keywords: value })} />
            <Field label="Đối tượng đọc" value={brief.audience} onChange={(value) => setBrief({ ...brief, audience: value })} />
            <Field label="Mục tiêu bài viết" value={brief.objective} onChange={(value) => setBrief({ ...brief, objective: value })} />
            <Field label="Category" value={brief.category} onChange={(value) => setBrief({ ...brief, category: value })} />
            <label className="text-sm font-medium text-slate-700">Độ dài mục tiêu
              <input className="input mt-2" type="number" min={300} max={3000} value={brief.targetLength} onChange={(event) => setBrief({ ...brief, targetLength: Number(event.target.value) })} />
            </label>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Nội dung bắt buộc" multiline value={brief.mustCover} onChange={(value) => setBrief({ ...brief, mustCover: value })} />
            <Field label="Nội dung cần tránh" multiline value={brief.mustAvoid} onChange={(value) => setBrief({ ...brief, mustAvoid: value })} />
          </div>
          <button className="btn btn-primary btn-lg" disabled={!brief.topic || !brief.keywords || !brief.audience || !brief.objective} onClick={createPlan}><Wand2 size={18} /> Tạo outline</button>
        </section>
      )}

      {stage === "planning" && <Working icon={<Search size={20} />} title="Đang tạo outline" />}

      {stage === "outline" && run && (
        <section className="max-w-4xl">
          <div className="mb-4"><div className="text-xs font-semibold uppercase text-emerald-700">Outline ready</div><h2 className="mt-1 text-xl font-semibold">{run.planned_title}</h2></div>
          <textarea className="input min-h-[360px] resize-y font-mono leading-7" value={outlineText} onChange={(event) => setOutlineText(event.target.value)} />
          <div className="mt-4 flex justify-end"><button className="btn btn-primary btn-lg" onClick={generate}><PenLine size={18} /> Viết và kiểm tra</button></div>
        </section>
      )}

      {stage === "generating" && <Working icon={<PenLine size={20} />} title="Writer và quality gate đang chạy" />}

      {stage === "result" && run && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
          <article className="rounded-md border border-slate-200 bg-white p-7 prose prose-slate max-w-none"><HighlightedBlog content={run.final_content ?? ""} evaluation={run.quality_report.final_evaluation} /></article>
          <aside className="space-y-5">
            <section className="rounded-md border border-slate-200 bg-white p-4">
              <div className="mb-3 flex items-center gap-2"><CheckCircle2 size={18} className={run.quality_report.passed ? "text-emerald-600" : "text-amber-600"} /><h3 className="font-semibold">Quality report</h3></div>
              <div className="space-y-2 text-sm">
                {Object.entries(run.quality_report.dimension_scores ?? {}).map(([key, value]) => <Metric key={key} label={key} value={value} />)}
              </div>
              <p className="mt-3 text-xs text-slate-500">Rewrite: {run.rewrite_count}/2</p>
              {(run.quality_report.violations ?? []).filter((item) => item.code !== "grounding_below_threshold").map((item) => <div key={item.code} className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">{item.code}</div>)}
            </section>
            <section className="rounded-md border border-slate-200 bg-white p-4">
              <h3 className="mb-3 font-semibold">Lý do chấm điểm</h3>
              <FinalEvaluationPanel evaluation={run.quality_report.final_evaluation} />
            </section>
            <section className="rounded-md border border-slate-200 bg-white p-4">
              <h3 className="mb-3 font-semibold">Nguồn đã dùng</h3>
              <div className="space-y-3 text-xs text-slate-600">
                {run.citations.length === 0 && <p>Không có knowledge citation.</p>}
                {run.citations.map((item) => <div key={`${item.document_id}-${item.excerpt}`}><div className="font-semibold text-slate-800">{item.document_id} · {Math.round((item.relevance_score ?? 0) * 100)}%</div><p className="mt-1 line-clamp-3">{item.excerpt}</p></div>)}
              </div>
            </section>
            <Link className="btn btn-primary w-full" href={`/review?run=${run.run_id}`}><FileCheck2 size={17} /> Chuyển sang duyệt</Link>
          </aside>
        </div>
      )}
    </main>
  );
}

function Field({ label, value, onChange, multiline = false }: { label: string; value: string; onChange: (value: string) => void; multiline?: boolean }) {
  return <label className="text-sm font-medium text-slate-700">{label}{multiline ? <textarea className="input mt-2 min-h-28 resize-y" value={value} onChange={(event) => onChange(event.target.value)} /> : <input className="input mt-2" value={value} onChange={(event) => onChange(event.target.value)} />}</label>;
}

function Working({ icon, title }: { icon: React.ReactNode; title: string }) {
  return <div className="flex min-h-[420px] items-center justify-center"><div className="flex items-center gap-3 text-slate-600"><Loader2 className="animate-spin text-emerald-600" size={22} />{icon}<span className="font-medium">{title}</span></div></div>;
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div><div className="mb-1 flex justify-between"><span className="capitalize text-slate-500">{label.replaceAll("_", " ")}</span><span className="font-semibold">{value}</span></div><div className="h-1.5 overflow-hidden rounded bg-slate-100"><div className={`h-full ${value >= 80 ? "bg-emerald-500" : value >= 60 ? "bg-amber-500" : "bg-rose-500"}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div></div>;
}
