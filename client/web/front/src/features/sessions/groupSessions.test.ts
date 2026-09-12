import { expect, it } from "vitest";
import type { SessionSummary } from "../../api/types";
import { groupSessionsByDate } from "./groupSessions";

it("将会话按今天、昨天和更早分组", () => {
  const now = new Date("2026-09-12T12:00:00+08:00");
  const session = (id: string, updatedAt: string): SessionSummary => ({
    id,
    title: id,
    conversationMode: "DIRECT",
    status: "ACTIVE",
    agent: { id: "agent_1", name: "工程师" },
    lastMessage: null,
    lastSequenceNo: null,
    createdAt: updatedAt,
    updatedAt,
  });

  const groups = groupSessionsByDate([
    session("today", "2026-09-12T08:00:00+08:00"),
    session("yesterday", "2026-09-11T20:00:00+08:00"),
    session("older", "2026-09-01T08:00:00+08:00"),
  ], now);

  expect(groups.map((group) => [group.label, group.sessions.map((item) => item.id)])).toEqual([
    ["今天", ["today"]],
    ["昨天", ["yesterday"]],
    ["更早", ["older"]],
  ]);
});
