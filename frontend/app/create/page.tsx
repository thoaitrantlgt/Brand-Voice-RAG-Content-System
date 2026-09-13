"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, CheckCircle2, FileCheck2, Loader2, PenLine, Search, Sparkles, Wand2 } from "lucide-react";
import { api, Job, waitForJob } from "../lib/api";
import { useProject } from "../components/ProjectContext";
import { FinalEvaluation, FinalEvaluationPanel, HighlightedBlog, ScoreBreakdown } from "../components/FinalEvaluation";
import { SeoEvaluation, SeoEvaluationPanel, SeoResearch } from "../components/SeoEvaluation";

type Run = {
  run_id: string;
  status: string;
  planned_title?: string | null;
  planned_seo_title?: string | null;
  meta_description?: string | null;
  outline: string[];
  final_content?: string | null;
  quality_report: {
    passed?: boolean;
    dimension_scores?: Record<string, number>;
    violations?: { code: string; actual?: number; threshold?: number }[];
    final_evaluation?: FinalEvaluation;
    score_breakdown?: ScoreBreakdown;
    seo_evaluation?: SeoEvaluation;
    seo_research?: SeoResearch;
  };
  citations: { document_id: string; source_url?: string | null; excerpt: string; relevance_score?: number }[];
  rewrite_count: number;
};

type Brief = {
  topic: string;
  keywords: string;
  audience: string;
  objective: string;
  category: string;
  mustCover: string;
  mustAvoid: string;
  targetLength: number;
  primaryKeyword: string;
  searchIntent: "auto" | "informational" | "commercial" | "navigational" | "transactional";
  seoResearch: boolean;
};

type BriefPreset = {
  id: string;
  label: string;
  description: string;
  replaceAll: boolean;
  values: Brief | Partial<Brief>;
};

type DraftStatus = "loading" | "saved" | "unavailable";

const DEMO_BRIEF: Brief = {
  topic: "Cách kiểm soát hơi khi hát cho người mới",
  keywords: "kiểm soát hơi, hỗ trợ hơi thở, luyện thanh",
  audience: "Học viên thanh nhạc mới bắt đầu",
  objective: "Hướng dẫn người đọc nhận biết và cải thiện cách lấy hơi khi hát",
  category: "Kỹ thuật thanh nhạc",
  mustCover: "dấu hiệu hụt hơi, bài tập kiểm soát luồng hơi",
  mustAvoid: "cam kết kết quả tuyệt đối, thuật ngữ quá hàn lâm",
  targetLength: 800,
  primaryKeyword: "kiểm soát hơi",
  searchIntent: "informational",
  seoResearch: false,
};

const BRIEF_PRESETS: BriefPreset[] = [
  {
    id: "demo-tss",
    label: "Demo TSS",
    description: "Điền toàn bộ form bằng dữ liệu mẫu thanh nhạc.",
    replaceAll: true,
    values: DEMO_BRIEF,
  },
  {
    id: "how-to",
    label: "Bài hướng dẫn",
    description: "Cấu hình bài hướng dẫn từng bước, dễ áp dụng.",
    replaceAll: false,
    values: {
      objective: "Hướng dẫn người đọc hiểu vấn đề và áp dụng các bước thực hành cụ thể",
      category: "Hướng dẫn",
      mustCover: "giải thích dễ hiểu, các bước thực hiện, ví dụ thực tế",
      mustAvoid: "thuật ngữ khó hiểu, cam kết kết quả tuyệt đối",
      targetLength: 800,
    },
  },
  {
    id: "problem-solving",
    label: "Giải quyết vấn đề",
    description: "Cấu hình bài phân tích dấu hiệu, nguyên nhân và cách khắc phục.",
    replaceAll: false,
    values: {
      objective: "Giúp người đọc nhận biết nguyên nhân và lựa chọn cách xử lý phù hợp",
      category: "Giải pháp",
      mustCover: "dấu hiệu nhận biết, nguyên nhân thường gặp, cách khắc phục",
      mustAvoid: "hù dọa người đọc, cam kết kết quả tuyệt đối",
      targetLength: 900,
    },
  },
  {
    id: "solution-intro",
    label: "Giới thiệu giải pháp",
    description: "Cấu hình bài giới thiệu lợi ích và đối tượng phù hợp.",
    replaceAll: false,
    values: {
      objective: "Giới thiệu giải pháp và giúp người đọc đánh giá mức độ phù hợp",
      category: "Giải pháp",
      mustCover: "vấn đề cần giải quyết, lợi ích chính, đối tượng phù hợp, bước tiếp theo",
      mustAvoid: "quảng cáo phóng đại, thông tin không kiểm chứng",
      targetLength: 1000,
    },
  },
];

const BRIEF_STORAGE_PREFIX = "contentos_brief_draft:";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseStoredBrief(raw: string | null): Brief | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    const candidate = isRecord(parsed) && isRecord(parsed.brief) ? parsed.brief : parsed;
    if (!isRecord(candidate)) return null;
    const storedLength = candidate.targetLength;
    return {
      topic: typeof candidate.topic === "string" ? candidate.topic : DEMO_BRIEF.topic,
      keywords: typeof candidate.keywords === "string" ? candidate.keywords : DEMO_BRIEF.keywords,
      audience: typeof candidate.audience === "string" ? candidate.audience : DEMO_BRIEF.audience,
      objective: typeof candidate.objective === "string" ? candidate.objective : DEMO_BRIEF.objective,
      category: typeof candidate.category === "string" ? candidate.category : DEMO_BRIEF.category,
      mustCover: typeof candidate.mustCover === "string" ? candidate.mustCover : DEMO_BRIEF.mustCover,
      mustAvoid: typeof candidate.mustAvoid === "string" ? candidate.mustAvoid : DEMO_BRIEF.mustAvoid,
      targetLength: typeof storedLength === "number" && Number.isInteger(storedLength) && storedLength >= 300 && storedLength <= 3000
        ? storedLength
        : DEMO_BRIEF.targetLength,
      primaryKeyword: typeof candidate.primaryKeyword === "string" ? candidate.primaryKeyword : DEMO_BRIEF.primaryKeyword,
      searchIntent: ["auto", "informational", "commercial", "navigational", "transactional"].includes(String(candidate.searchIntent))
        ? candidate.searchIntent as Brief["searchIntent"]
        : DEMO_BRIEF.searchIntent,
      seoResearch: typeof candidate.seoResearch === "boolean" ? candidate.seoResearch : false,
    };
  } catch {
    return null;
  }
}

export default function CreatePage() {
  const { projectId, loading: projectLoading } = useProject();
  const [brief, setBrief] = useState<Brief>({ ...DEMO_BRIEF });
  const [loadedProjectId, setLoadedProjectId] = useState<string | null>(null);
  const [draftStatus, setDraftStatus] = useState<DraftStatus>("loading");
  const [run, setRun] = useState<Run | null>(null);
  const [outlineText, setOutlineText] = useState("");
  const [stage, setStage] = useState<"brief" | "planning" | "outline" | "generating" | "result">("brief");
  const [error, setError] = useState("");

  useEffect(() => {
    if (projectLoading) return;
    const timer = window.setTimeout(() => {
      try {
        const stored = window.localStorage.getItem(BRIEF_STORAGE_PREFIX + projectId);
        setBrief(parseStoredBrief(stored) ?? { ...DEMO_BRIEF });
        setDraftStatus("saved");
      } catch {
        setBrief({ ...DEMO_BRIEF });
        setDraftStatus("unavailable");
      }
      setLoadedProjectId(projectId);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [projectId, projectLoading]);

  useEffect(() => {
    if (projectLoading || loadedProjectId !== projectId) return;
    const timer = window.setTimeout(() => {
      try {
        window.localStorage.setItem(
          BRIEF_STORAGE_PREFIX + projectId,
          JSON.stringify({ version: 1, brief }),
        );
        setDraftStatus("saved");
      } catch {
        setDraftStatus("unavailable");
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [brief, loadedProjectId, projectId, projectLoading]);

  const list = (value: string) => value.split(/[,\n]/).map((item) => item.trim()).filter(Boolean);

  const applyPreset = (preset: BriefPreset) => {
    setBrief((current) => preset.replaceAll
      ? { ...(preset.values as Brief) }
      : { ...current, ...preset.values });
  };

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
          primary_keyword: brief.primaryKeyword || list(brief.keywords)[0],
          search_intent: brief.searchIntent,
          seo_research_enabled: brief.seoResearch,
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
          <div className="rounded-md border border-indigo-200 bg-indigo-50/70 p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 className="flex items-center gap-2 text-sm font-semibold text-indigo-950"><Sparkles size={16} /> Nhập nhanh</h2>
                <p className="mt-1 text-xs leading-5 text-indigo-700">Mẫu chung giữ nguyên Chủ đề, Từ khóa và Đối tượng đọc.</p>
              </div>
              <div className={"flex shrink-0 items-center gap-1.5 text-xs " + (draftStatus === "unavailable" ? "text-amber-700" : "text-emerald-700")}>
                {draftStatus === "loading" ? <Loader2 className="animate-spin" size={14} /> : draftStatus === "saved" ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                {draftStatus === "loading" ? "Đang tải bản nháp" : draftStatus === "saved" ? "Đã tự lưu" : "Không thể tự lưu"}
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {BRIEF_PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  title={preset.description}
                  className="rounded-md border border-indigo-200 bg-white px-3 py-2 text-xs font-semibold text-indigo-800 shadow-sm transition hover:border-indigo-300 hover:bg-indigo-100"
                  onClick={() => applyPreset(preset)}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Chủ đề" value={brief.topic} onChange={(value) => setBrief({ ...brief, topic: value })} />
            <Field label="Từ khóa" value={brief.keywords} onChange={(value) => setBrief({ ...brief, keywords: value })} />
            <Field label="Từ khóa chính" value={brief.primaryKeyword} onChange={(value) => setBrief({ ...brief, primaryKeyword: value })} />
            <label className="text-sm font-medium text-slate-700">Search intent
              <select className="input mt-2" value={brief.searchIntent} onChange={(event) => setBrief({ ...brief, searchIntent: event.target.value as Brief["searchIntent"] })}>
                <option value="auto">Tự suy luận</option><option value="informational">Tìm hiểu</option><option value="commercial">So sánh giải pháp</option><option value="transactional">Thực hiện giao dịch</option><option value="navigational">Tìm trang cụ thể</option>
              </select>
            </label>
            <Field label="Đối tượng đọc" value={brief.audience} onChange={(value) => setBrief({ ...brief, audience: value })} />
            <Field label="Mục tiêu bài viết" value={brief.objective} onChange={(value) => setBrief({ ...brief, objective: value })} />
            <Field label="Category" value={brief.category} onChange={(value) => setBrief({ ...brief, category: value })} />
            <label className="text-sm font-medium text-slate-700">Độ dài mục tiêu
              <input className="input mt-2" type="number" min={300} max={3000} value={brief.targetLength} onChange={(event) => setBrief({ ...brief, targetLength: Number(event.target.value) })} />
            </label>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={brief.seoResearch} onChange={(event) => setBrief({ ...brief, seoResearch: event.target.checked })} /> Nghiên cứu web khi lập outline SEO</label>
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
              <SeoEvaluationPanel evaluation={run.quality_report.seo_evaluation} seoTitle={run.planned_seo_title} metaDescription={run.meta_description} modelReason={run.quality_report.final_evaluation?.dimensions.find((item) => item.metric === "seo")?.reason} research={run.quality_report.seo_research} />
            </section>
            <section className="rounded-md border border-slate-200 bg-white p-4">
              <h3 className="mb-3 font-semibold">Lý do chấm điểm</h3>
              <FinalEvaluationPanel evaluation={run.quality_report.final_evaluation} scoreBreakdown={run.quality_report.score_breakdown} />
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
