import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { EmptyState } from "../../../components/EmptyState";
import { ErrorState } from "../../../components/ErrorState";
import { Skeleton } from "../../../components/Skeleton";
import { listAgents } from "../../agents/api";
import { createSession } from "../../sessions/api";
import { NewSessionDialog } from "../components/NewSessionDialog";

/** 新建 DIRECT 会话；确认角色和工作目录后才创建 Session。 */
export function NewChatPage() {
  const [params] = useSearchParams();
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(params.get("agentId"));
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const create = useMutation({
    mutationFn: () => {
      if (!selectedAgentId) throw new Error("请选择一个角色");
      return createSession({ mode: "DIRECT", agentId: selectedAgentId, title: null, workspacePath });
    },
    onSuccess: (session) => {
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      navigate(`/sessions/${encodeURIComponent(session.id)}`, { replace: true });
    },
  });

  useEffect(() => {
    setSelectedAgentId(params.get("agentId"));
  }, [params]);

  const close = () => {
    if (!create.isPending) navigate(-1);
  };

  return (
    <div className="workspace-page new-chat-page">
      <header className="workspace-header"><div><p className="eyebrow">新对话</p><h1>配置会话</h1></div></header>
      <div className="new-chat-page__body">
        {agents.isLoading && <div className="new-chat-page__picker"><Skeleton rows={3} /></div>}
        {agents.isError && <div className="new-chat-page__picker"><ErrorState message={agents.error.message} onRetry={() => { void agents.refetch(); }} /></div>}
        {agents.data?.items.length === 0 && <EmptyState icon={<Bot />} title="没有可用角色" description="需要先启用至少一个角色才能开始对话。" />}
      </div>
      {agents.data && agents.data.items.length > 0 && (
        <NewSessionDialog
          agents={agents.data.items}
          selectedAgentId={selectedAgentId}
          workspacePath={workspacePath}
          isSubmitting={create.isPending}
          error={create.isError ? create.error.message : null}
          onAgentSelect={setSelectedAgentId}
          onWorkspaceChange={setWorkspacePath}
          onConfirm={() => { create.mutate(); }}
          onClose={close}
        />
      )}
    </div>
  );
}
