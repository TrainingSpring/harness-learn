import { Bot } from "lucide-react";
import { Link } from "react-router-dom";
import type { AgentReference } from "../../../api/types";

/** 对话顶部固定显示当前唯一角色和运行状态。 */
export function ChatHeader({ agent, status }: { agent: AgentReference; status: "idle" | "running" | "waiting" }) {
  const statusText = status === "running" ? "正在回复" : status === "waiting" ? "等待权限确认" : "可用";
  return (
    <header className="chat-header">
      <Link className="chat-header__agent" to={`/agents/${encodeURIComponent(agent.id)}`}>
        <span className="avatar avatar--small"><Bot size={15} /></span>
        <span><strong>{agent.name}</strong><small>{statusText}</small></span>
      </Link>
      <span className={`run-status run-status--${status}`}><i />{statusText}</span>
    </header>
  );
}
