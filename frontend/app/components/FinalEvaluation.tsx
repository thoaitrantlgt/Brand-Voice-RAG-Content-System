"use client";

import { Children, ReactNode } from "react";
import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";

export type FinalDimension = {
  metric: string;
  score: number | null;
  threshold?: number | null;
  gated?: boolean;
  passed?: boolean | null;
  status?: "evaluated" | "not_applicable" | "unavailable" | "disabled" | "error";
  reason: string;
};

export type FinalAnnotation = {
  quote: string;
  metric: string;
  severity: "error" | "warning" | "info";
  reason: string;
  suggestion: string;
  start: number;
  end: number;
  line: number;
  column: number;
};

export type FinalEvaluation = {
  status: "evaluated" | "error" | "disabled";
  provider: string;
  model: string;
  overall_score: number;
  passed: boolean;
  summary: string;
  dimensions: FinalDimension[];
  annotations: FinalAnnotation[];
  error?: string;
};

const severityClass = {
  error: "bg-rose-200 text-rose-950 ring-1 ring-inset ring-rose-300",
  warning: "bg-amber-200 text-amber-950 ring-1 ring-inset ring-amber-300",
  info: "bg-sky-200 text-sky-950 ring-1 ring-inset ring-sky-300",
};

function highlightedText(text: string, annotations: FinalAnnotation[]): ReactNode[] {
  const lowered = text.toLocaleLowerCase("vi");
  const matches: { start: number; end: number; annotation: FinalAnnotation }[] = [];
  for (const annotation of annotations) {
    const quote = annotation.quote.trim();
    if (!quote) continue;
    const index = lowered.indexOf(quote.toLocaleLowerCase("vi"));
    if (index >= 0) matches.push({ start: index, end: index + quote.length, annotation });
  }
  matches.sort((left, right) => left.start - right.start || right.end - left.end);

  const output: ReactNode[] = [];
  let cursor = 0;
  for (const match of matches) {
    if (match.start < cursor) continue;
    if (match.start > cursor) output.push(text.slice(cursor, match.start));
    const { annotation } = match;
    output.push(
      <mark
        key={`${annotation.start}-${annotation.metric}-${match.start}`}
        className={`rounded-sm px-0.5 ${severityClass[annotation.severity]}`}
        title={`${annotation.metric}: ${annotation.reason}`}
      >
        {text.slice(match.start, match.end)}
      </mark>,
    );
    cursor = match.end;
  }
  if (cursor < text.length) output.push(text.slice(cursor));
  return output.length ? output : [text];
}

function highlightedChildren(children: ReactNode, annotations: FinalAnnotation[]) {
  return Children.map(children, (child) =>
    typeof child === "string" ? highlightedText(child, annotations) : child,
  );
}

export function HighlightedBlog({ content, evaluation }: { content: string; evaluation?: FinalEvaluation }) {
  const annotations = evaluation?.status === "evaluated" ? evaluation.annotations.filter((item) => item.metric !== "grounding") : [];
  const components: Components = {
    p: ({ children }) => <p>{highlightedChildren(children, annotations)}</p>,
    li: ({ children }) => <li>{highlightedChildren(children, annotations)}</li>,
    h1: ({ children }) => <h1>{highlightedChildren(children, annotations)}</h1>,
    h2: ({ children }) => <h2>{highlightedChildren(children, annotations)}</h2>,
    h3: ({ children }) => <h3>{highlightedChildren(children, annotations)}</h3>,
    blockquote: ({ children }) => <blockquote>{highlightedChildren(children, annotations)}</blockquote>,
    strong: ({ children }) => <strong>{highlightedChildren(children, annotations)}</strong>,
    em: ({ children }) => <em>{highlightedChildren(children, annotations)}</em>,
  };
  return <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{content}</ReactMarkdown>;
}

export function FinalEvaluationPanel({ evaluation }: { evaluation?: FinalEvaluation }) {
  if (!evaluation) return <p className="text-xs text-slate-500">Chưa có đánh giá cuối từ model.</p>;
  if (evaluation.status !== "evaluated") {
    return <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">{evaluation.summary}{evaluation.error ? ` ${evaluation.error}` : ""}</div>;
  }

  const hadLegacyGrounding = evaluation.dimensions.some((item) => item.metric === "grounding");
  const dimensions = evaluation.dimensions.filter((item) => item.metric !== "grounding");
  const annotations = evaluation.annotations.filter((item) => item.metric !== "grounding");
  const numericScores = dimensions.flatMap((item) => typeof item.score === "number" ? [item.score] : []);
  const overallScore = hadLegacyGrounding && numericScores.length > 0
    ? Math.round(numericScores.reduce((total, score) => total + score, 0) / numericScores.length)
    : evaluation.overall_score;
  const passed = hadLegacyGrounding
    ? dimensions.every((item) => item.gated === false || item.passed !== false)
    : evaluation.passed;
  const summary = hadLegacyGrounding
    ? "Đánh giá cuối dựa trên Brand, Style, Fingerprint và Persona."
    : evaluation.summary;

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3">
        {passed ? <CheckCircle2 className="mt-0.5 shrink-0 text-emerald-600" size={18} /> : <AlertTriangle className="mt-0.5 shrink-0 text-amber-600" size={18} />}
        <div>
          <div className="flex flex-wrap items-center gap-2"><strong className="text-sm">Đánh giá cuối: {overallScore}/100</strong><span className="text-[11px] text-slate-400">{evaluation.model}</span></div>
          <p className="mt-1 text-xs leading-5 text-slate-600">{summary}</p>
        </div>
      </div>

      <div className="divide-y divide-slate-100 border-y border-slate-100">
        {dimensions.map((dimension) => (
          <div key={dimension.metric} className="py-3">
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="flex items-center gap-1.5 font-semibold capitalize text-slate-700">
                {dimension.gated === false ? <Info size={13} className="text-sky-600" /> : dimension.passed ? <CheckCircle2 size={13} className="text-emerald-600" /> : <XCircle size={13} className="text-rose-600" />}
                {dimension.metric.replaceAll("_", " ")}
              </span>
              <span className="font-semibold">{dimension.score ?? "N/A"}</span>
            </div>
            <p className="mt-1.5 text-xs leading-5 text-slate-500">{dimension.reason}</p>
          </div>
        ))}
      </div>

      <div>
        <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Vị trí nên cải thiện</h4>
        {annotations.length === 0 && <p className="text-xs text-slate-500">Model không xác định đoạn cụ thể nào cần chỉnh thêm.</p>}
        <div className="space-y-2">
          {annotations.map((annotation) => (
            <div key={`${annotation.start}-${annotation.metric}`} className={`rounded-md px-3 py-2 text-xs ${severityClass[annotation.severity]}`}>
              <div className="flex items-center justify-between gap-3 font-semibold"><span className="capitalize">{annotation.metric.replaceAll("_", " ")}</span><span>Dòng {annotation.line}, cột {annotation.column}</span></div>
              <p className="mt-1 font-medium">“{annotation.quote}”</p>
              <p className="mt-1.5 leading-5">{annotation.reason}</p>
              {annotation.suggestion && <p className="mt-1.5 leading-5"><strong>Gợi ý:</strong> {annotation.suggestion}</p>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
