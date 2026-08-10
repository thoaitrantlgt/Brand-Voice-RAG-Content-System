"use client";

import { Loader2 } from "lucide-react";
import Sidebar from "./Sidebar";
import { ProjectProvider, useProject } from "./ProjectContext";

function ProjectContent({ children }: { children: React.ReactNode }) {
  const { projectId, loading } = useProject();
  if (loading) {
    return (
      <div className="flex min-w-0 flex-1 items-center justify-center px-5 pb-16 pt-14 md:py-0">
        <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white px-6 py-8 text-center shadow-sm">
          <Loader2 className="mx-auto mb-4 animate-spin text-emerald-600" size={30} />
          <h1 className="text-base font-semibold text-slate-900">Đang tải workspace demo</h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">Đang khởi tạo project và 10 writing samples. Lần đầu có thể mất vài giây.</p>
        </div>
      </div>
    );
  }
  return <div key={projectId} className="min-w-0 flex-1 overflow-y-auto pb-16 pt-14 md:py-0">{children}</div>;
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ProjectProvider>
      <div className="flex min-h-screen bg-[#f5f6f8] text-slate-900">
        <Sidebar />
        <ProjectContent>{children}</ProjectContent>
      </div>
    </ProjectProvider>
  );
}
