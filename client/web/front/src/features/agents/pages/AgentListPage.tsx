import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Plus } from "lucide-react";
import { useState } from "react";
import { Button } from "../../../components/Button";
import { EmptyState } from "../../../components/EmptyState";
import { ErrorState } from "../../../components/ErrorState";
import { Skeleton } from "../../../components/Skeleton";
import { createAgent, generateAgentProfileSuggestion, getAgent, listAgents, updateAgent } from "../api";
import { AgentCard } from "../components/AgentCard";
import { CreateAgentDialog } from "../components/CreateAgentDialog";
import type { AgentDetail } from "../../../api/types";
import { listLlmProfiles, listMcpServers, listSkills, listTools } from "../../settings/api";

/** 已启用角色的发现页。 */
export function AgentListPage() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentDetail | null>(null);
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const llmProfiles = useQuery({ queryKey: ["llm-profiles"], queryFn: listLlmProfiles });
  const tools = useQuery({ queryKey: ["tools"], queryFn: listTools });
  const skills = useQuery({ queryKey: ["skills"], queryFn: listSkills });
  const mcpServers = useQuery({ queryKey: ["mcp-servers"], queryFn: listMcpServers });
  const createMutation = useMutation({
    mutationFn: createAgent,
    onSuccess: async () => {
      await agents.refetch();
      setIsCreateOpen(false);
    },
  });
  const suggestionMutation = useMutation({ mutationFn: generateAgentProfileSuggestion });
  const updateMutation = useMutation({
    mutationFn: (request: Parameters<typeof updateAgent>[1]) => updateAgent(editingAgent!.id, request),
    onSuccess: async () => { await agents.refetch(); setEditingAgent(null); },
  });

  const openEdit = async (agentId: string) => {
    const agent = await getAgent(agentId);
    setEditingAgent(agent);
  };

  return (
    <div className="page page--wide">
      <header className="page-header"><div><p className="eyebrow">角色目录</p><h1>选择适合当前任务的角色</h1><p>每个角色拥有独立的模型、专长、工具和权限配置。</p></div><Button variant="primary" icon={<Plus size={16} />} onClick={() => setIsCreateOpen(true)}>新增角色</Button></header>
      {agents.isLoading && <Skeleton rows={6} />}
      {agents.isError && <ErrorState message={agents.error.message} onRetry={() => { void agents.refetch(); }} />}
      {agents.data?.items.length === 0 && <EmptyState icon={<Bot />} title="尚未配置角色" description="请先通过配置层添加并启用角色。" />}
      {agents.data && agents.data.items.length > 0 && <div className="agent-grid">{agents.data.items.map((agent) => <AgentCard key={agent.id} agent={agent} onEdit={(id) => { void openEdit(id); }} />)}</div>}
      <CreateAgentDialog
        isOpen={isCreateOpen}
        isSubmitting={createMutation.isPending}
        error={createMutation.error?.message ?? null}
        llmProfiles={llmProfiles.data?.items ?? []}
        tools={tools.data?.items ?? []}
        skills={skills.data?.items.filter((skill) => skill.status === "AVAILABLE") ?? []}
        mcpServers={mcpServers.data?.items ?? []}
        isSuggesting={suggestionMutation.isPending}
        onClose={() => { if (!createMutation.isPending) setIsCreateOpen(false); }}
        onSubmit={(request) => { createMutation.mutate(request); }}
        onSuggest={(request) => suggestionMutation.mutateAsync(request)}
      />
      <CreateAgentDialog
        key={editingAgent?.id ?? "no-edit"}
        isOpen={Boolean(editingAgent)}
        initialAgent={editingAgent}
        submitLabel="保存修改"
        isSubmitting={updateMutation.isPending}
        error={updateMutation.error?.message ?? null}
        llmProfiles={llmProfiles.data?.items ?? []}
        tools={tools.data?.items ?? []}
        skills={skills.data?.items ?? []}
        mcpServers={mcpServers.data?.items ?? []}
        isSuggesting={suggestionMutation.isPending}
        onClose={() => { if (!updateMutation.isPending) setEditingAgent(null); }}
        onSubmit={(request) => { updateMutation.mutate(request); }}
        onSuggest={(request) => suggestionMutation.mutateAsync(request)}
      />
    </div>
  );
}
