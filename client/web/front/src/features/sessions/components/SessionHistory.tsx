import type { SessionSummary } from "../../../api/types";
import { groupSessionsByDate } from "../groupSessions";
import { SessionHistoryItem } from "./SessionHistoryItem";

/** 按本地日期分组的会话历史列表。 */
export function SessionHistory({ sessions, currentSessionId }: { sessions: SessionSummary[]; currentSessionId: string | null }) {
  return (
    <nav className="session-history" aria-label="历史会话">
      {groupSessionsByDate(sessions).map((group) => (
        <section key={group.label}>
          <h2>{group.label}</h2>
          {group.sessions.map((session) => <SessionHistoryItem key={session.id} session={session} active={session.id === currentSessionId} />)}
        </section>
      ))}
    </nav>
  );
}
