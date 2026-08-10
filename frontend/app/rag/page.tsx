"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Database, FileText, Loader2, Plus, RefreshCw, Trash2, Upload, Volume2 } from "lucide-react";
import { api, Job, waitForJob } from "../lib/api";
import { useProject } from "../components/ProjectContext";

type Cluster = "knowledge" | "brand_voice" | "evaluation";
type Document = { document_id: string; filename: string; cluster: Cluster; total_chunks: number; status: string; approval_status: string; human_rating?: number | null };
type Profile = { profile_id: string; name: string; version: number; status: string; is_active: boolean; source_document_ids: string[]; created_at: string };

const tabs: { id: Cluster; label: string }[] = [
  { id: "knowledge", label: "Knowledge" },
  { id: "brand_voice", label: "Writing samples" },
  { id: "evaluation", label: "Evaluation" },
];

export default function SourcesPage() {
  const { projectId, refresh: refreshProjects } = useProject();
  const [cluster, setCluster] = useState<Cluster>("brand_voice");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [documentPayload, profilePayload] = await Promise.all([
        api<{ documents: Document[] }>(`/documents?project_id=${encodeURIComponent(projectId)}`),
        api<Profile[]>(`/projects/${projectId}/profiles`),
      ]);
      setDocuments(documentPayload.documents);
      setProfiles(profilePayload);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Không thể tải dữ liệu"); }
    finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const upload = async (file: File) => {
    setBusy(true); setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("purpose", cluster);
      body.append("cluster", cluster);
      body.append("project_id", projectId);
      await api("/documents/upload", { method: "POST", body });
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Upload failed"); }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const approve = async (documentId: string) => {
    await api(`/projects/${projectId}/documents/${documentId}/approval`, {
      method: "POST", body: JSON.stringify({ status: "approved", human_rating: 5 }),
    });
    await load();
  };

  const remove = async (documentId: string) => {
    if (!window.confirm("Xóa tài liệu này?")) return;
    await api(`/documents/${documentId}`, { method: "DELETE" });
    await load();
  };

  const train = async () => {
    setBusy(true); setError("");
    try {
      const queued = await api<{ job: Job }>(`/projects/${projectId}/profiles/train`, {
        method: "POST",
        body: JSON.stringify({ name: "Main", min_documents: 5, max_documents: 30, document_ids: [] }),
      });
      await waitForJob(queued.job.job_id, 360_000);
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Profile training failed"); }
    finally { setBusy(false); }
  };

  const createProject = async () => {
    const id = window.prompt("Project ID (a-z, 0-9, -, _)");
    if (!id) return;
    const name = window.prompt("Project name", id);
    if (!name) return;
    await api("/projects", { method: "POST", body: JSON.stringify({ project_id: id, name }) });
    await refreshProjects();
  };

  const visible = documents.filter((item) => item.cluster === cluster);
  const approvedSamples = documents.filter((item) => item.cluster === "brand_voice" && (item.approval_status === "approved" || (item.human_rating ?? 0) >= 4)).length;

  return (
    <main className="mx-auto max-w-6xl px-5 py-7 lg:px-8">
      <header className="mb-6 flex items-start justify-between border-b border-slate-200 pb-5">
        <div><h1 className="text-2xl font-semibold">Nguồn và Brand Profile</h1><p className="mt-1 text-sm text-slate-500">{projectId}</p></div>
        <div className="flex gap-2"><button className="btn btn-secondary" onClick={createProject}><Plus size={16} /> Project</button><button className="btn btn-secondary" title="Refresh" onClick={() => void load()}><RefreshCw size={16} /></button></div>
      </header>
      {error && <div className="mb-5 rounded-md bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

      <div className="mb-5 flex border-b border-slate-200">
        {tabs.map((tab) => <button key={tab.id} className={`border-b-2 px-4 py-3 text-sm font-medium ${cluster === tab.id ? "border-emerald-600 text-emerald-700" : "border-transparent text-slate-500"}`} onClick={() => setCluster(tab.id)}>{tab.label}</button>)}
      </div>

      <section className="mb-9">
        <div className="mb-4 flex items-center justify-between"><h2 className="font-semibold">Tài liệu · {loading ? "Đang tải..." : visible.length}</h2><label className="btn btn-primary"><Upload size={16} /> Upload<input ref={fileRef} className="hidden" type="file" accept=".pdf,.txt,.md,.docx" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); }} /></label></div>
        <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
          <table className="w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">File</th><th className="px-4 py-3">Index</th><th className="px-4 py-3">Approval</th><th className="w-24 px-4 py-3"></th></tr></thead><tbody className="divide-y divide-slate-100">
            {loading && <tr><td colSpan={4} className="px-4 py-12 text-center text-slate-500"><Loader2 className="mx-auto mb-3 animate-spin text-emerald-600" size={24} /><span className="font-medium text-slate-700">Đang tải tài liệu và 10 writing samples...</span><span className="mt-1 block text-xs text-slate-400">Dữ liệu sẽ tự hiển thị ngay khi tải xong.</span></td></tr>}
            {!loading && visible.map((document) => <tr key={document.document_id}><td className="px-4 py-3"><div className="flex items-center gap-2"><FileText size={16} className="text-slate-400" /><span className="font-medium">{document.filename}</span></div></td><td className="px-4 py-3 text-slate-500">{document.total_chunks} chunks · {document.status}</td><td className="px-4 py-3">{cluster === "brand_voice" ? <span className={`badge ${document.approval_status === "approved" ? "badge-green" : "badge-amber"}`}>{document.approval_status}</span> : <span className="text-slate-400">-</span>}</td><td className="px-4 py-3"><div className="flex justify-end gap-1">{cluster === "brand_voice" && document.approval_status !== "approved" && <button className="btn btn-ghost p-2" title="Approve sample" onClick={() => void approve(document.document_id)}><Check size={16} /></button>}<button className="btn btn-ghost btn-danger p-2" title="Delete" onClick={() => void remove(document.document_id)}><Trash2 size={16} /></button></div></td></tr>)}
            {!loading && visible.length === 0 && <tr><td colSpan={4} className="px-4 py-12 text-center text-slate-400"><Database className="mx-auto mb-2" size={24} />Chưa có tài liệu</td></tr>}
          </tbody></table>
        </div>
      </section>

      <section>
        <div className="mb-4 flex items-center justify-between"><div><h2 className="font-semibold">Brand Profile versions</h2><p className="mt-1 text-xs text-slate-500">Approved samples: {loading ? "Đang tải..." : approvedSamples}</p></div><button className="btn btn-primary" disabled={loading || busy || approvedSamples < 5} onClick={() => void train()}>{busy ? <Loader2 className="animate-spin" size={16} /> : <Volume2 size={16} />} Train profile</button></div>
        <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
          {loading && <div className="flex items-center justify-center gap-2 px-4 py-12 text-sm text-slate-500"><Loader2 className="animate-spin text-emerald-600" size={18} />Đang tải profile...</div>}
          {!loading && profiles.map((profile) => <div key={profile.profile_id} className="flex items-center gap-4 border-b border-slate-100 px-4 py-4 last:border-0"><div className="flex h-9 w-9 items-center justify-center rounded-md bg-emerald-50 text-emerald-700"><Volume2 size={17} /></div><div className="min-w-0 flex-1"><div className="font-medium">{profile.name} v{profile.version}</div><div className="text-xs text-slate-500">{profile.source_document_ids.length} samples · {profile.profile_id}</div></div><span className={`badge ${profile.is_active ? "badge-green" : "badge-blue"}`}>{profile.status}</span>{!profile.is_active && <button className="btn btn-secondary" onClick={async () => { await api(`/projects/${projectId}/profiles/${profile.profile_id}/activate`, { method: "POST" }); await load(); }}>Activate</button>}</div>)}
          {!loading && profiles.length === 0 && <div className="px-4 py-12 text-center text-sm text-slate-400">Chưa có profile version</div>}
        </div>
      </section>
    </main>
  );
}
