import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, MessageSquare, ShieldCheck, Wrench } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ErrorState } from "../../../components/ErrorState";
import { Skeleton } from "../../../components/Skeleton";
import { getAgent } from "../api";

/** 单个角色的运行配置概览；敏感凭据不进入浏览器契约。 */
export function AgentDetailPage() {
  const { agentId = "" } = useParams();
  const agent = useQuery({ queryKey: ["agent", agentId], queryFn: () => getAgent(agentId), enabled: Boolean(agentId) });
  if (agent.isLoading) return <div className="page"><Skeleton rows={5} /></div>;
  if (agent.isError) return <div className="page"><ErrorState message={agent.error.message} onRetry={() => { void agent.refetch(); }} /></div>;
  if (!agent.data) return null;

  return (
    <div className="page page--narrow">
      <Link className="back-link" to="/agents"><ArrowLeft size={15} />返回角色列表</Link>
      <header className="profile-header">
        <div className="avatar avatar--large" aria-hidden="true">{agent.data.name.slice(0, 1)}</div>
        <div><p className="eyebrow">角色详情</p><h1>{agent.data.name}</h1><p>{agent.data.description}</p></div>
      </header>
      <section className="detail-section"><h2>角色特征</h2><p>{agent.data.personality || "未设置"}</p><div className="tag-row">{agent.data.expertise.map((item) => <span className="tag" key={item}>{item}</span>)}</div></section>
      <section className="detail-section"><h2><Wrench size={17} />可用工具</h2><div className="plain-list">{agent.data.tools.map((tool) => <code key={tool}>{tool}</code>)}</div></section>
      <section className="detail-section detail-grid">
        <div><h2><ShieldCheck size={17} />权限模式</h2><p>{agent.data.permissionMode}</p></div>
        <div><h2>LLM 配置</h2><p><code>{agent.data.llmProfileId}</code></p></div>
      </section>
      <Link className="button button--primary profile-action" to={`/new?agentId=${encodeURIComponent(agent.data.id)}`}><MessageSquare size={16} />与该角色对话</Link>
    </div>
  );
}
