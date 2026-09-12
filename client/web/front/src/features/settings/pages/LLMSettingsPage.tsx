import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Plus } from "lucide-react";
import { useState } from "react";
import { Button } from "../../../components/Button";
import { EmptyState } from "../../../components/EmptyState";
import { ErrorState } from "../../../components/ErrorState";
import { Skeleton } from "../../../components/Skeleton";
import { createLlmProfile, listLlmProfiles } from "../api";
import { CreateLlmDialog } from "../components/CreateLlmDialog";

/** LLM 配置只读列表，不展示凭据引用和值。 */
export function LLMSettingsPage() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const profiles = useQuery({ queryKey: ["llm-profiles"], queryFn: listLlmProfiles });
  const createMutation = useMutation({
    mutationFn: createLlmProfile,
    onSuccess: async () => {
      await profiles.refetch();
      setIsCreateOpen(false);
    },
  });
  return <div className="settings-section"><div className="settings-section__header"><div><h2>LLM 配置</h2><p>角色可引用的模型连接配置。凭据仅显示配置状态。</p></div><Button variant="primary" icon={<Plus size={16} />} onClick={() => setIsCreateOpen(true)}>新增配置</Button></div>
    {profiles.isLoading && <Skeleton rows={4} />}
    {profiles.isError && <ErrorState message={profiles.error.message} onRetry={() => { void profiles.refetch(); }} />}
    {profiles.data?.items.length === 0 && <EmptyState icon={<Bot />} title="尚未配置 LLM" description="当前没有可供角色使用的模型配置。" />}
    {profiles.data && profiles.data.items.length > 0 && <div className="data-table" role="table" aria-label="LLM 配置">
      <div className="data-table__row data-table__head" role="row"><span>名称</span><span>服务商 / 模型</span><span>地址</span><span>凭据</span></div>
      {profiles.data.items.map((profile) => <div className="data-table__row" role="row" key={profile.id}><strong>{profile.name}</strong><span>{profile.provider}<small>{profile.model}</small></span><code>{profile.baseUrl}</code><span className={`status ${profile.hasCredential ? "status--ok" : "status--muted"}`}>{profile.hasCredential ? "已配置" : "未配置"}</span></div>)}
    </div>}
    <CreateLlmDialog isOpen={isCreateOpen} isSubmitting={createMutation.isPending} error={createMutation.error?.message ?? null} onClose={() => { if (!createMutation.isPending) setIsCreateOpen(false); }} onSubmit={(request) => { createMutation.mutate(request); }} />
  </div>;
}
