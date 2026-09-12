import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Plus } from "lucide-react";
import { useState } from "react";
import { Button } from "../../../components/Button";
import { EmptyState } from "../../../components/EmptyState";
import { ErrorState } from "../../../components/ErrorState";
import { Skeleton } from "../../../components/Skeleton";
import { createAgent, generateAgentProfileSuggestion, listAgents } from "../api";
import { AgentCard } from "../components/AgentCard";
import { CreateAgentDialog } from "../components/CreateAgentDialog";
import { listLlmProfiles, listTools } from "../../settings/api";

/** 已启用角色的发现页。 */
export function AgentListPage() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const llmProfiles = useQuery({ queryKey: ["llm-profiles"], queryFn: listLlmProfiles });
  const tools = useQuery({ queryKey: ["tools"], queryFn: listTools });
  const createMutation = useMutation({
    mutationFn: createAgent,
    onSuccess: async () => {
      await agents.refetch();
      setIsCreateOpen(false);
    },
  });
  const suggestionMutation = useMutation({ mutationFn: generateAgentProfileSuggestion });

  return (
    <div className="page page--wide">
      <header className="page-header"><div><p className="eyebrow">角色目录</p><h1>选择适合当前任务的角色</h1><p>每个角色拥有独立的模型、专长、工具和权限配置。</p></div><Button variant="primary" icon={<Plus size={16} />} onClick={() => setIsCreateOpen(true)}>新增角色</Button></header>
      {agents.isLoading && <Skeleton rows={6} />}
      {agents.isError && <ErrorState message={agents.error.message} onRetry={() => { void agents.refetch(); }} />}
      {agents.data?.items.length === 0 && <EmptyState icon={<Bot />} title="尚未配置角色" description="请先通过配置层添加并启用角色。" />}
      {agents.data && agents.data.items.length > 0 && <div className="agent-grid">{agents.data.items.map((agent) => <AgentCard key={agent.id} agent={agent} />)}</div>}
      <CreateAgentDialog
        isOpen={isCreateOpen}
        isSubmitting={createMutation.isPending}
        error={createMutation.error?.message ?? null}
        llmProfiles={llmProfiles.data?.items ?? []}
        tools={tools.data?.items ?? []}
        isSuggesting={suggestionMutation.isPending}
        onClose={() => { if (!createMutation.isPending) setIsCreateOpen(false); }}
        onSubmit={(request) => { createMutation.mutate(request); }}
        onSuggest={(request) => suggestionMutation.mutateAsync(request)}
      />
    </div>
  );
}
