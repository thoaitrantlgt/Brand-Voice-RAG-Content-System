"use client";

import Sidebar from "./Sidebar";
import { ProjectProvider, useProject } from "./ProjectContext";

function ProjectContent({ children }: { children: React.ReactNode }) {
  const { projectId } = useProject();
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
