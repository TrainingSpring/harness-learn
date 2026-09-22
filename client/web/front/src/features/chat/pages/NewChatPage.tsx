import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import { useEffect, useState } from "react";
import type { PermissionMode } from "../../../api/types";
import { useNavigate, useSearchParams } from "react-router-dom";
import { EmptyState } from "../../../components/EmptyState";
import { ErrorState } from "../../../components/ErrorState";
import { Skeleton } from "../../../components/Skeleton";
import { listAgents } from "../../agents/api";
import { AgentPicker } from "../../agents/components/AgentPicker";
import { createSession } from "../../sessions/api";
import { Composer } from "../components/Composer";

/** 选择固定角色并在第一条消息发送时创建 DIRECT 会话。 */
export function NewChatPage() {
  const [params] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(params.get("agentId"));
  const [permissionMode, setPermissionMode] = useState<PermissionMode>("plan");
  const [projectPath, setProjectPath] = useState<string | null>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const create = useMutation({
    mutationFn: ({ agentId, text }: { agentId: string; text: string }) => createSession({ mode: "DIRECT", agentId, title: null, permissionMode, projectPath }).then((session) => ({ session, text })),
    onSuccess: ({ session, text }) => {
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      navigate(`/sessions/${encodeURIComponent(session.id)}`, { replace: true, state: { initialMessage: text } });
    },
  });

  useEffect(() => {
    const requested = params.get("agentId");
    if (requested) setSelectedId(requested);
  }, [params]);

  const selected = agents.data?.items.find((agent) => agent.id === selectedId) ?? null;
  return (
    <div className="workspace-page new-chat-page">
      <header className="workspace-header"><div><p className="eyebrow">新对话</p><h1>{selected ? `与 ${selected.name} 对话` : "选择一个角色"}</h1></div></header>
      <div className="new-chat-page__body">
        <div className="new-chat-page__picker">
          <p className="section-label">可用角色</p>
          {agents.isLoading && <Skeleton rows={3} />}
          {agents.isError && <ErrorState message={agents.error.message} onRetry={() => { void agents.refetch(); }} />}
          {agents.data?.items.length === 0 && <EmptyState icon={<Bot />} title="没有可用角色" description="需要先启用至少一个角色才能开始对话。" />}
          {agents.data && <AgentPicker agents={agents.data.items} selectedId={selectedId} onSelect={setSelectedId} />}
        </div>
      </div>
      <footer className="composer-dock">
        {create.isError && <p className="inline-error" role="alert">{create.error.message}</p>}
        {selected ? (
          <Composer autoFocus isRunning={create.isPending} onStop={() => undefined} onSend={(text) => create.mutate({ agentId: selected.id, text })} placeholder={`发消息给 ${selected.name}`} projectPath={projectPath} isProjectLocked={false} permissionMode={permissionMode} onProjectChange={setProjectPath} onPermissionModeChange={setPermissionMode} />
        ) : (
          <div className="composer-placeholder">选择角色后即可输入消息</div>
        )}
      </footer>
    </div>
  );
}
