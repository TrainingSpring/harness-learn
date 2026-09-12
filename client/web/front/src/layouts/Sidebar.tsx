import { useQuery } from "@tanstack/react-query";
import { Bot, Settings, SquarePen } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { listSessions } from "../features/sessions/api";
import { SessionHistory } from "../features/sessions/components/SessionHistory";
import { Skeleton } from "../components/Skeleton";

/** 桌面与移动抽屉共用的主导航内容。 */
export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const location = useLocation();
  const currentSessionId = location.pathname.match(/^\/sessions\/([^/]+)/)?.[1] ?? null;
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: listSessions });

  return (
    <aside className="sidebar" aria-label="主导航">
      <div className="sidebar__brand"><span className="brand-mark">H</span><span>Harness</span></div>
      <nav className="sidebar__primary" onClick={onNavigate}>
        <NavLink to="/new"><SquarePen size={17} />新对话</NavLink>
        <NavLink to="/agents"><Bot size={17} />角色</NavLink>
      </nav>
      <div className="sidebar__history">
        {sessions.isLoading && <Skeleton rows={4} />}
        {sessions.isError && <p className="sidebar__notice">会话记录暂时不可用</p>}
        {sessions.data?.items.length === 0 && <p className="sidebar__notice">还没有对话记录</p>}
        {sessions.data && <SessionHistory sessions={sessions.data.items} currentSessionId={currentSessionId} />}
      </div>
      <nav className="sidebar__footer" onClick={onNavigate}>
        <NavLink to="/settings/appearance"><Settings size={17} />设置</NavLink>
      </nav>
    </aside>
  );
}
