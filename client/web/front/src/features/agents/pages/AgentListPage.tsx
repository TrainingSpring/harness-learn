import { useQuery } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import { EmptyState } from "../../../components/EmptyState";
import { ErrorState } from "../../../components/ErrorState";
import { Skeleton } from "../../../components/Skeleton";
import { listAgents } from "../api";
import { AgentCard } from "../components/AgentCard";

/** 已启用角色的发现页。 */
export function AgentListPage() {
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  return (
    <div className="page page--wide">
      <header className="page-header"><div><p className="eyebrow">角色目录</p><h1>选择适合当前任务的角色</h1><p>每个角色拥有独立的模型、专长、工具和权限配置。</p></div></header>
      {agents.isLoading && <Skeleton rows={6} />}
      {agents.isError && <ErrorState message={agents.error.message} onRetry={() => { void agents.refetch(); }} />}
      {agents.data?.items.length === 0 && <EmptyState icon={<Bot />} title="尚未配置角色" description="请先通过配置层添加并启用角色。" />}
      {agents.data && agents.data.items.length > 0 && <div className="agent-grid">{agents.data.items.map((agent) => <AgentCard key={agent.id} agent={agent} />)}</div>}
    </div>
  );
}
