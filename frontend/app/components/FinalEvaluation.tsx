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
  deductions?: FinalDeduction[];
};

export type FinalDeduction = {
  criterion: string;
  points: number;
  reason: string;
  suggestion?: string;
};

export type ScoreBreakdown = Record<string, { criterion: string; score: number; reason?: string; suggestion?: string }[]>;

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

const metricLabels: Record<string, string> = {
  brand: "Brand",
  style: "Style",
  fingerprint: "Fingerprint",
  persona: "Persona",
};

function allocatePoints(weights: number[], total: number) {
  if (weights.length === 0 || total <= 0) return weights.map(() => 0);
  const normalized = weights.map((weight) => Math.max(0, weight));
  const weightSum = normalized.reduce((sum, weight) => sum + weight, 0) || normalized.length;
  const exact = normalized.map((weight) => total * (weightSum === normalized.length && normalized.every((item) => item === 0) ? 1 : weight) / weightSum);
  const allocated = exact.map(Math.floor);
  let remainder = total - allocated.reduce((sum, points) => sum + points, 0);
  const order = exact.map((value, index) => ({ index, fraction: value - allocated[index], weight: normalized[index] })).sort((left, right) => right.fraction - left.fraction || right.weight - left.weight);
  for (const item of order) {
    if (remainder <= 0) break;
    allocated[item.index] += 1;
    remainder -= 1;
  }
  return allocated;
}

function deductionsFromComponents(dimension: FinalDimension, scoreBreakdown?: ScoreBreakdown): FinalDeduction[] {
  if (typeof dimension.score !== "number") return [];
  const totalDeducted = Math.max(0, 100 - dimension.score);
  const components = (scoreBreakdown?.[dimension.metric] ?? []).filter((item) => item.score < 100);
  if (components.length === 0 || totalDeducted === 0) return [];
  const points = allocatePoints(components.map((item) => 100 - item.score), totalDeducted);
  return components.flatMap((component, index) => {
    if (points[index] <= 0) return [];
    const normalizedCriterion = component.criterion.toLocaleLowerCase("vi");
    const modelDetail = dimension.deductions?.find((item) => {
      const candidate = item.criterion.toLocaleLowerCase("vi");
      return candidate.includes(normalizedCriterion) || normalizedCriterion.includes(candidate);
    });
    return [{
      criterion: component.criterion,
      points: points[index],
      reason: modelDetail?.reason ?? component.reason ?? `Điểm thành phần đạt ${component.score}/100, chưa khớp hoàn toàn với profile.`,
      suggestion: modelDetail?.suggestion ?? component.suggestion ?? `Ưu tiên cải thiện tiêu chí ${component.criterion.toLocaleLowerCase("vi")} trong lần chỉnh sửa tiếp theo.`,
    }];
  });
}

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
  const perfectMetrics = new Set(
    evaluation?.dimensions.filter((item) => item.score === 100).map((item) => item.metric) ?? [],
  );
  const annotations = evaluation?.status === "evaluated" ? evaluation.annotations.filter((item) => item.metric !== "grounding" && !perfectMetrics.has(item.metric)) : [];
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

export function FinalEvaluationPanel({ evaluation, scoreBreakdown }: { evaluation?: FinalEvaluation; scoreBreakdown?: ScoreBreakdown }) {
  if (!evaluation) return <p className="text-xs text-slate-500">Chưa có đánh giá cuối từ model.</p>;
  if (evaluation.status !== "evaluated") {
    return <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">{evaluation.summary}{evaluation.error ? ` ${evaluation.error}` : ""}</div>;
  }

  const hadLegacyGrounding = evaluation.dimensions.some((item) => item.metric === "grounding");
  const dimensions = evaluation.dimensions.filter((item) => item.metric !== "grounding");
  const perfectMetrics = new Set(dimensions.filter((item) => item.score === 100).map((item) => item.metric));
  const annotations = evaluation.annotations.filter((item) => item.metric !== "grounding" && !perfectMetrics.has(item.metric));
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

      <div className="space-y-3">
        {dimensions.map((dimension) => {
          const totalDeducted = typeof dimension.score === "number" ? Math.max(0, 100 - dimension.score) : 0;
          const dimensionReason = dimension.score === 100
            ? `${metricLabels[dimension.metric] ?? dimension.metric} đạt 100/100; không có tiêu chí nào bị trừ điểm.`
            : dimension.reason;
          const componentDeductions = deductionsFromComponents(dimension, scoreBreakdown);
          const deductions = componentDeductions.length
            ? componentDeductions
            : dimension.deductions?.length
            ? dimension.deductions
            : totalDeducted > 0
              ? [{ criterion: metricLabels[dimension.metric] ?? dimension.metric, points: totalDeducted, reason: dimensionReason, suggestion: "Đối chiếu với profile và chỉnh các vùng được đánh dấu bên dưới." }]
              : [];
          return (
            <div key={dimension.metric} className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="flex items-center gap-1.5 font-semibold text-slate-700">
                  {dimension.gated === false ? <Info size={13} className="text-sky-600" /> : dimension.passed ? <CheckCircle2 size={13} className="text-emerald-600" /> : <XCircle size={13} className="text-rose-600" />}
                  {metricLabels[dimension.metric] ?? dimension.metric.replaceAll("_", " ")}
                </span>
                <span className="font-semibold text-slate-900">{dimension.score ?? "N/A"}/100</span>
              </div>
              <p className="mt-1.5 text-xs leading-5 text-slate-600">{dimensionReason}</p>

              {typeof dimension.score === "number" && dimension.score === 100 && (
                <div className="mt-2 rounded-md bg-emerald-50 px-2.5 py-2 text-[11px] font-medium text-emerald-700">Không bị trừ điểm ở nhóm này.</div>
              )}
              {deductions.length > 0 && (
                <div className="mt-3 space-y-2 border-t border-slate-200 pt-3">
                  <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    <span>Chi tiết trừ điểm</span><span className="text-rose-600">-{totalDeducted} điểm</span>
                  </div>
                  {deductions.map((deduction, index) => (
                    <div key={`${dimension.metric}-${deduction.criterion}-${index}`} className="rounded-md border border-rose-100 bg-white px-2.5 py-2 text-xs">
                      <div className="flex items-start justify-between gap-2 font-semibold text-slate-700"><span>{deduction.criterion}</span><span className="shrink-0 text-rose-600">-{deduction.points} điểm</span></div>
                      <p className="mt-1 leading-5 text-slate-500">{deduction.reason}</p>
                      {deduction.suggestion && <p className="mt-1 leading-5 text-emerald-700"><strong>Cách cải thiện:</strong> {deduction.suggestion}</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
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
