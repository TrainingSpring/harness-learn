import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, createBrowserRouter } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { Skeleton } from "../components/Skeleton";
import { listSessions } from "../features/sessions/api";
import { AppShell } from "../layouts/AppShell";

const AgentListPage = lazy(() => import("../features/agents/pages/AgentListPage").then((module) => ({ default: module.AgentListPage })));
const AgentDetailPage = lazy(() => import("../features/agents/pages/AgentDetailPage").then((module) => ({ default: module.AgentDetailPage })));
const NewChatPage = lazy(() => import("../features/chat/pages/NewChatPage").then((module) => ({ default: module.NewChatPage })));
const ChatPage = lazy(() => import("../features/chat/pages/ChatPage").then((module) => ({ default: module.ChatPage })));
const SettingsLayout = lazy(() => import("../features/settings/pages/SettingsLayout").then((module) => ({ default: module.SettingsLayout })));
const AppearanceSettingsPage = lazy(() => import("../features/settings/pages/AppearanceSettingsPage").then((module) => ({ default: module.AppearanceSettingsPage })));
const LLMSettingsPage = lazy(() => import("../features/settings/pages/LLMSettingsPage").then((module) => ({ default: module.LLMSettingsPage })));
const ToolSettingsPage = lazy(() => import("../features/settings/pages/ToolSettingsPage").then((module) => ({ default: module.ToolSettingsPage })));

function deferred(page: ReactNode) {
  return <Suspense fallback={<div className="page"><Skeleton rows={5} /></div>}>{page}</Suspense>;
}

/** 根路径优先恢复最近会话；没有历史或查询失败时进入新对话。 */
function HomeRedirect() {
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: listSessions });
  if (sessions.isLoading) return null;
  const latest = sessions.data?.items[0];
  return <Navigate replace to={latest ? `/sessions/${encodeURIComponent(latest.id)}` : "/new"} />;
}

function NotFoundPage() {
  return <div className="page"><EmptyState title="页面不存在" description="当前地址没有对应的工作区页面。" /></div>;
}

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <HomeRedirect /> },
      { path: "/new", element: deferred(<NewChatPage />) },
      { path: "/sessions/:sessionId", element: deferred(<ChatPage />) },
      { path: "/agents", element: deferred(<AgentListPage />) },
      { path: "/agents/:agentId", element: deferred(<AgentDetailPage />) },
      {
        path: "/settings",
        element: deferred(<SettingsLayout />),
        children: [
          { index: true, element: <Navigate replace to="appearance" /> },
          { path: "appearance", element: deferred(<AppearanceSettingsPage />) },
          { path: "llms", element: deferred(<LLMSettingsPage />) },
          { path: "tools", element: deferred(<ToolSettingsPage />) },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
