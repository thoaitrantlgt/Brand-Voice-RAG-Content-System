"use client";

import { AlertCircle, CheckCircle2, Info, Search } from "lucide-react";

export type SeoCheck = {
  code: string;
  status: "passed" | "needs_attention" | "advisory";
  severity: "warning" | "info";
  evidence: string;
  recommendation: string;
};

export type SeoFieldIssue = {
  field: string;
  current_value: string;
  reason: string;
  suggestion: string;
};

export type SeoEvaluation = {
  status: "evaluated" | "disabled" | "error";
  score: number;
  threshold: number;
  gated: boolean;
  included_in_overall: boolean;
  primary_keyword: string;
  search_intent: string;
  subscores: Record<string, number>;
  checks: SeoCheck[];
  field_issues: SeoFieldIssue[];
};

export type SeoResearch = {
  query_variations: string[];
  sources: { query: string; title: string; url: string; snippet: string; domain: string }[];
  source_urls: string[];
};

const labels: Record<string, string> = {
  search_intent_satisfaction: "Search intent satisfaction",
  helpful_completeness: "Helpful completeness",
  information_gain_originality: "Information gain & originality",
  evidence_expertise_trust: "Evidence, expertise & trust",
  title_snippet_accuracy: "Title & snippet accuracy",
  semantic_topic_coverage: "Semantic topic coverage",
  structure_scannability: "Structure & scannability",
  title_h1_quality: "Title & H1 check",
  snippet_quality: "Snippet check",
  keyword_usage: "Keyword usage",
  content_structure: "Structure check",
};

export function SeoEvaluationPanel({
  evaluation,
  seoTitle,
  metaDescription,
  modelReason,
  research,
}: {
  evaluation?: SeoEvaluation;
  seoTitle?: string | null;
  metaDescription?: string | null;
  modelReason?: string;
  research?: SeoResearch;
}) {
  if (!evaluation) {
    return <p className="text-xs text-slate-500">Chưa có đánh giá SEO cho bài này.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Search size={16} className="text-emerald-700" />
            <strong className="text-sm">SEO Readiness</strong>
          </div>
          <p className="mt-1 text-[11px] text-slate-500">
            Tham khảo, không dự đoán thứ hạng và không tính vào điểm tổng.
          </p>
        </div>
        <span className={`text-lg font-semibold ${evaluation.score >= evaluation.threshold ? "text-emerald-700" : "text-amber-700"}`}>
          {evaluation.score}/100
        </span>
      </div>

      {modelReason && <p className="text-xs leading-5 text-slate-600">{modelReason}</p>}

      <div className="rounded-md border border-slate-200 bg-white p-3">
        <div className="flex items-start justify-between gap-2"><p className="min-w-0 truncate text-[13px] text-sky-800">{seoTitle || "Chưa có SEO title"}</p><span className="shrink-0 text-[10px] text-slate-400">{seoTitle?.length ?? 0} ký tự</span></div>
        <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">
          {metaDescription || "Chưa có meta description"}
        </p>
        <p className="mt-1 text-right text-[10px] text-slate-400">{metaDescription?.length ?? 0} ký tự · chỉ tham khảo</p>
        <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-slate-400">
          <span>Keyword: {evaluation.primary_keyword || "chưa chọn"}</span>
          <span>Intent: {evaluation.search_intent}</span>
        </div>
      </div>

      <div className="space-y-2">
        {Object.entries(evaluation.subscores).map(([key, value]) => (
          <div key={key}>
            <div className="mb-1 flex items-center justify-between text-[11px]">
              <span className="text-slate-600">{labels[key] ?? key.replaceAll("_", " ")}</span>
              <strong>{value}</strong>
            </div>
            <div className="h-1.5 overflow-hidden rounded bg-slate-100">
              <div className={`h-full ${value >= 75 ? "bg-emerald-500" : value >= 55 ? "bg-amber-500" : "bg-rose-500"}`} style={{ width: `${value}%` }} />
            </div>
          </div>
        ))}
      </div>

      {research && research.sources.length > 0 && (
        <div className="space-y-2 border-t border-slate-100 pt-3">
          <h4 className="text-[11px] font-semibold uppercase text-slate-500">Web research provenance</h4>
          {research.sources.map((source) => (
            <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className="block border-b border-slate-100 py-2 last:border-b-0 hover:text-emerald-800">
              <span className="block truncate text-xs font-semibold text-sky-800">{source.title || source.domain}</span>
              {source.snippet && <span className="mt-1 line-clamp-2 block text-[11px] leading-4 text-slate-500">{source.snippet}</span>}
              <span className="mt-1 block truncate text-[10px] text-slate-400">{source.domain} · query: {source.query}</span>
            </a>
          ))}
        </div>
      )}

      {evaluation.field_issues.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-[11px] font-semibold uppercase text-slate-500">Title & snippet</h4>
          {evaluation.field_issues.map((issue) => (
            <div key={`${issue.field}-${issue.reason}`} className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs">
              <div className="flex items-center gap-1.5 font-semibold text-amber-900"><AlertCircle size={13} />{issue.field.replaceAll("_", " ")}</div>
              <p className="mt-1 leading-5 text-amber-800">{issue.reason}</p>
              <p className="mt-1 leading-5 text-emerald-800"><strong>Cách cải thiện:</strong> {issue.suggestion}</p>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-2">
        <h4 className="text-[11px] font-semibold uppercase text-slate-500">Kiểm tra SEO</h4>
        {evaluation.checks.every((item) => item.status === "passed") && (
          <div className="flex items-center gap-2 rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-800"><CheckCircle2 size={14} />Không có cảnh báo SEO quan trọng.</div>
        )}
        {evaluation.checks.map((check) => (
          <div key={check.code} className="border-t border-slate-100 py-2 text-xs first:border-t-0">
            <div className="flex items-center gap-1.5 font-semibold text-slate-700">{check.status === "passed" ? <CheckCircle2 size={13} className="text-emerald-600" /> : <Info size={13} className="text-amber-600" />}{labels[check.code] ?? check.code.replaceAll("_", " ")}</div>
            <p className="mt-1 leading-5 text-slate-500">{check.evidence}</p>
            <p className="mt-1 leading-5 text-emerald-700"><strong>Cách cải thiện:</strong> {check.recommendation}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
