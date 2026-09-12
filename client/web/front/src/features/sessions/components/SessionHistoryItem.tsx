import { Link } from "react-router-dom";
import type { SessionSummary } from "../../../api/types";

/** 侧栏中的单条会话摘要。 */
export function SessionHistoryItem({ session, active }: { session: SessionSummary; active: boolean }) {
  const title = session.title || session.lastMessage || "未命名对话";
  return (
    <Link className={`session-item ${active ? "session-item--active" : ""}`} to={`/sessions/${encodeURIComponent(session.id)}`} aria-current={active ? "page" : undefined} title={title}>
      <span className="session-item__title">{title}</span>
      <span className="session-item__agent">{session.agent.name}</span>
    </Link>
  );
}
