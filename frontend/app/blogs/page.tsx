"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Edit3, ExternalLink, FileText, RefreshCw, Trash2, X } from "lucide-react";
import { api } from "../lib/api";
import { useProject } from "../components/ProjectContext";

type Blog = { id: number; title: string; seo_title?: string | null; meta_description?: string | null; content: string; keywords?: string | null; status: string; generation_run_id?: string | null; approved_by?: string | null; created_at: string; updated_at: string };

export default function BlogsPage() {
  const { projectId } = useProject();
  const [blogs, setBlogs] = useState<Blog[]>([]);
  const [editing, setEditing] = useState<Blog | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try { setBlogs(await api<Blog[]>(`/blogs?project_id=${encodeURIComponent(projectId)}`)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Không thể tải bài viết"); }
  }, [projectId]);

  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);

  const save = async () => {
    if (!editing || editing.status === "published") return;
    await api(`/blogs/${editing.id}`, { method: "PUT", body: JSON.stringify({ title: editing.title, seo_title: editing.seo_title, meta_description: editing.meta_description, content: editing.content, keywords: editing.keywords }) });
    setEditing(null); await load();
  };

  const remove = async (blog: Blog) => {
    if (!window.confirm(`Xóa “${blog.title}”?`)) return;
    await api(`/blogs/${blog.id}`, { method: "DELETE" }); await load();
  };

  return (
    <main className="mx-auto max-w-6xl px-5 py-7 lg:px-8">
      <header className="mb-6 flex items-start justify-between border-b border-slate-200 pb-5"><div><h1 className="text-2xl font-semibold">Bài viết</h1><p className="mt-1 text-sm text-slate-500">{projectId} · {blogs.length} bài</p></div><div className="flex gap-2"><button className="btn btn-secondary" title="Refresh" onClick={() => void load()}><RefreshCw size={16} /></button><Link href="/create" className="btn btn-primary">Tạo bài</Link></div></header>
      {error && <div className="mb-5 rounded-md bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      <div className="overflow-hidden rounded-md border border-slate-200 bg-white"><table className="w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">Bài viết</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Approval</th><th className="px-4 py-3">Updated</th><th className="w-28 px-4 py-3"></th></tr></thead><tbody className="divide-y divide-slate-100">
        {blogs.map((blog) => <tr key={blog.id}><td className="px-4 py-4"><div className="flex items-start gap-3"><FileText size={17} className="mt-0.5 text-slate-400" /><div><div className="font-medium">{blog.title}</div><div className="mt-1 text-xs text-slate-400">{blog.generation_run_id || "manual draft"}</div></div></div></td><td className="px-4 py-4"><span className={`badge ${blog.status === "published" ? "badge-green" : "badge-amber"}`}>{blog.status}</span></td><td className="px-4 py-4 text-slate-500">{blog.approved_by || "-"}</td><td className="px-4 py-4 text-xs text-slate-500">{new Date(blog.updated_at).toLocaleDateString("vi-VN")}</td><td className="px-4 py-4"><div className="flex justify-end gap-1"><button className="btn btn-ghost p-2" title="Open" onClick={() => setEditing({ ...blog })}>{blog.status === "published" ? <ExternalLink size={16} /> : <Edit3 size={16} />}</button><button className="btn btn-ghost btn-danger p-2" title="Delete" onClick={() => void remove(blog)}><Trash2 size={16} /></button></div></td></tr>)}
        {blogs.length === 0 && <tr><td colSpan={5} className="px-4 py-14 text-center text-slate-400">Chưa có bài viết</td></tr>}
      </tbody></table></div>

      {editing && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-5"><div className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-md bg-white shadow-xl"><header className="flex items-center gap-3 border-b border-slate-200 px-5 py-4"><input className="input flex-1 text-base font-semibold" value={editing.title} readOnly={editing.status === "published"} onChange={(event) => setEditing({ ...editing, title: event.target.value })} /><button className="btn btn-ghost p-2" onClick={() => setEditing(null)}><X size={18} /></button></header><textarea className="min-h-[600px] flex-1 resize-none p-5 font-mono text-sm leading-7 outline-none" readOnly={editing.status === "published"} value={editing.content} onChange={(event) => setEditing({ ...editing, content: event.target.value })} />{editing.status !== "published" && <footer className="flex justify-end border-t border-slate-200 px-5 py-4"><button className="btn btn-primary" onClick={() => void save()}>Lưu draft</button></footer>}</div></div>}
    </main>
  );
}
