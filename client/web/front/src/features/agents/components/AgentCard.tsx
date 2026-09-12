import { ArrowRight, TerminalSquare } from "lucide-react";
import { Link } from "react-router-dom";
import type { AgentSummary } from "../../../api/types";

/** 角色发现页中的独立条目，强调职责和可用能力。 */
export function AgentCard({ agent }: { agent: AgentSummary }) {
  const visibleTools = agent.tools.slice(0, 3);
  const remaining = agent.tools.length - visibleTools.length;

  return (
    <article className="agent-card">
      <div className="agent-card__header">
        <div className="avatar" aria-hidden="true">{agent.name.slice(0, 1)}</div>
        <div>
          <h2>{agent.name}</h2>
          <p>{agent.personality || "未设置性格描述"}</p>
        </div>
      </div>
      <p className="agent-card__description">{agent.description}</p>
      <div className="tag-row" aria-label="擅长领域">
        {agent.expertise.map((item) => <span className="tag" key={item}>{item}</span>)}
      </div>
      <div className="agent-card__tools">
        <TerminalSquare size={15} aria-hidden="true" />
        {visibleTools.length > 0 ? visibleTools.join(" · ") : "未配置工具"}
        {remaining > 0 && <span>另有 {remaining} 项</span>}
      </div>
      <div className="agent-card__actions">
        <Link className="text-link" to={`/agents/${encodeURIComponent(agent.id)}`}>查看详情</Link>
        <Link className="button button--primary" aria-label={`与${agent.name}开始对话`} to={`/new?agentId=${encodeURIComponent(agent.id)}`}>
          开始对话 <ArrowRight size={15} />
        </Link>
      </div>
    </article>
  );
}
