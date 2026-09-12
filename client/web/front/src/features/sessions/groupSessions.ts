import type { SessionSummary } from "../../api/types";

export interface SessionGroup {
  label: "今天" | "昨天" | "更早";
  sessions: SessionSummary[];
}

function startOfDay(value: Date): number {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
}

/** 按用户本地日历日期分组，避免 UTC 日期让深夜会话落入错误分组。 */
export function groupSessionsByDate(sessions: SessionSummary[], now = new Date()): SessionGroup[] {
  const today = startOfDay(now);
  const dayMs = 24 * 60 * 60 * 1000;
  const groups: SessionGroup[] = [
    { label: "今天", sessions: [] },
    { label: "昨天", sessions: [] },
    { label: "更早", sessions: [] },
  ];

  sessions.forEach((session) => {
    const age = today - startOfDay(new Date(session.updatedAt));
    const index = age <= 0 ? 0 : age <= dayMs ? 1 : 2;
    groups[index].sessions.push(session);
  });
  return groups.filter((group) => group.sessions.length > 0);
}
