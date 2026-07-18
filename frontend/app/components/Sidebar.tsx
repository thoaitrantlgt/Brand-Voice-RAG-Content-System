"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";
import { useEffect, useState } from "react";
import { Activity, Database, FileCheck2, FileText, KeyRound, LayoutDashboard, PenTool, Zap } from "lucide-react";
import { health, setAccessToken } from "../lib/api";
import { useProject } from "./ProjectContext";

const nav = [
  { href: "/", icon: LayoutDashboard, label: "Tổng quan" },
  { href: "/create", icon: PenTool, label: "Tạo bài" },
  { href: "/review", icon: FileCheck2, label: "Duyệt bài" },
  { href: "/blogs", icon: FileText, label: "Bài đã lưu" },
  { href: "/rag", icon: Database, label: "Nguồn & Profile" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { projects, projectId, setProjectId, loading, refresh } = useProject();
  const [online, setOnline] = useState(false);

  useEffect(() => {
    const check = () => void health().then(() => setOnline(true)).catch(() => setOnline(false));
    check();
    const timer = window.setInterval(check, 15000);
    return () => window.clearInterval(timer);
  }, []);

  const configureToken = () => {
    const value = window.prompt("Internal access token");
    if (value === null) return;
    setAccessToken(value);
    void refresh();
  };

  return (
    <Fragment>
    <aside className="sticky top-0 hidden h-screen w-[232px] shrink-0 flex-col border-r border-zinc-800 bg-zinc-950 text-zinc-100 md:flex">
      <div className="flex h-16 items-center gap-3 border-b border-zinc-800 px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-emerald-500 text-zinc-950"><Zap size={17} /></div>
        <div><div className="text-sm font-semibold">ContentOS</div><div className="text-[11px] text-zinc-500">Internal workspace</div></div>
      </div>

      <div className="border-b border-zinc-800 p-3">
        <label className="mb-1 block text-[10px] font-semibold uppercase text-zinc-500">Project</label>
        <select
          className="h-9 w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 text-xs outline-none"
          value={projectId}
          disabled={loading}
          onChange={(event) => setProjectId(event.target.value)}
        >
          {projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.name}</option>)}
        </select>
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {nav.map(({ href, icon: Icon, label }) => (
          <Link key={href} href={href} className={`sidebar-link ${pathname === href ? "active" : ""}`}>
            <Icon size={16} /><span>{label}</span>
          </Link>
        ))}
      </nav>

      <div className="space-y-2 border-t border-zinc-800 p-3">
        <div className="flex items-center gap-2 rounded-md bg-zinc-900 px-3 py-2 text-xs text-zinc-400">
          <Activity size={14} className={online ? "text-emerald-400" : "text-rose-400"} />
          <span className="flex-1">{online ? "Backend online" : "Backend offline"}</span>
        </div>
        <button className="sidebar-link w-full" onClick={configureToken} title="Configure access token">
          <KeyRound size={16} /><span>Access token</span>
        </button>
      </div>
    </aside>
    <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center gap-3 border-b border-zinc-800 bg-zinc-950 px-3 text-white md:hidden">
      <Zap size={17} className="text-emerald-400" />
      <select className="h-8 min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-2 text-xs" value={projectId} onChange={(event) => setProjectId(event.target.value)}>{projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.name}</option>)}</select>
      <button className="p-2 text-zinc-400" onClick={configureToken} title="Access token"><KeyRound size={17} /></button>
    </header>
    <nav className="fixed inset-x-0 bottom-0 z-40 grid h-16 grid-cols-5 border-t border-zinc-800 bg-zinc-950 md:hidden">
      {nav.map(({ href, icon: Icon, label }) => <Link key={href} href={href} title={label} className={`flex items-center justify-center ${pathname === href ? "text-emerald-400" : "text-zinc-500"}`}><Icon size={19} /></Link>)}
    </nav>
    </Fragment>
  );
}
