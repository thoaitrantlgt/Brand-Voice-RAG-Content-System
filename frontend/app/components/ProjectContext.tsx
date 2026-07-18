"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";

export type Project = { project_id: string; name: string; description?: string | null };

type ProjectState = {
  projects: Project[];
  projectId: string;
  setProjectId: (value: string) => void;
  refresh: () => Promise<void>;
  loading: boolean;
};

const ProjectContext = createContext<ProjectState | null>(null);

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectIdState] = useState("default");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const items = await api<Project[]>("/projects");
      setProjects(items);
      const saved = window.localStorage.getItem("contentos_project");
      const next = items.some((item) => item.project_id === saved) ? saved! : items[0]?.project_id ?? "default";
      setProjectIdState(next);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  const setProjectId = (value: string) => {
    setProjectIdState(value);
    window.localStorage.setItem("contentos_project", value);
  };

  const value = useMemo(
    () => ({ projects, projectId, setProjectId, refresh, loading }),
    [projects, projectId, loading, refresh],
  );
  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject() {
  const value = useContext(ProjectContext);
  if (!value) throw new Error("useProject must be used inside ProjectProvider");
  return value;
}
