import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "../../../components/Button";
import { EmptyState } from "../../../components/EmptyState";
import { ErrorState } from "../../../components/ErrorState";
import { Skeleton } from "../../../components/Skeleton";
import type { LLMProfileSummary } from "../../../api/types";
import { createLlmProfile, deleteLlmProfile, listLlmProfiles, updateLlmProfile } from "../api";
import { CreateLlmDialog } from "../components/CreateLlmDialog";
import { DeleteLlmDialog } from "../components/DeleteLlmDialog";

/** LLM 配置管理页面，支持新增、修改和删除不暴露 API Key 的模型连接。 */
export function LLMSettingsPage() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingProfile, setEditingProfile] = useState<LLMProfileSummary | null>(null);
  const [deletingProfile, setDeletingProfile] = useState<LLMProfileSummary | null>(null);
  const profiles = useQuery({ queryKey: ["llm-profiles"], queryFn: listLlmProfiles });
  const createMutation = useMutation({
    mutationFn: createLlmProfile,
    onSuccess: async () => {
      await profiles.refetch();
      setIsCreateOpen(false);
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ profileId, request }: { profileId: string; request: Parameters<typeof updateLlmProfile>[1] }) => updateLlmProfile(profileId, request),
    onSuccess: async () => {
      await profiles.refetch();
      setEditingProfile(null);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteLlmProfile,
    onSuccess: async () => {
      await profiles.refetch();
      setDeletingProfile(null);
    },
  });
  return <div className="settings-section"><div className="settings-section__header"><div><h2>LLM 配置</h2><p>角色可引用的模型连接配置。API Key 仅显示配置状态。</p></div><Button variant="primary" icon={<Plus size={16} />} onClick={() => setIsCreateOpen(true)}>新增配置</Button></div>
    {profiles.isLoading && <Skeleton rows={4} />}
    {profiles.isError && <ErrorState message={profiles.error.message} onRetry={() => { void profiles.refetch(); }} />}
    {profiles.data?.items.length === 0 && <EmptyState icon={<Bot />} title="尚未配置 LLM" description="当前没有可供角色使用的模型配置。" />}
    {profiles.data && profiles.data.items.length > 0 && <div className="data-table data-table--llms" role="table" aria-label="LLM 配置">
      <div className="data-table__row data-table__head" role="row"><span>名称</span><span>服务商 / 模型</span><span>地址</span><span>API Key</span><span>操作</span></div>
      {profiles.data.items.map((profile) => <div className="data-table__row" role="row" key={profile.id}><strong>{profile.name}</strong><span>{profile.provider}<small>{profile.model}</small></span><code>{profile.baseUrl}</code><span className={`status ${profile.hasApiKey ? "status--ok" : "status--muted"}`}>{profile.hasApiKey ? "已配置" : "未配置"}</span><span className="table-actions"><button type="button" className="icon-button" aria-label={`编辑 ${profile.name}`} title="编辑配置" onClick={() => setEditingProfile(profile)}><Pencil size={16} /></button><button type="button" className="icon-button icon-button--danger" aria-label={`删除 ${profile.name}`} title="删除配置" onClick={() => setDeletingProfile(profile)}><Trash2 size={16} /></button></span></div>)}
    </div>}
    <CreateLlmDialog mode="create" isOpen={isCreateOpen} isSubmitting={createMutation.isPending} error={createMutation.error?.message ?? null} onClose={() => { if (!createMutation.isPending) setIsCreateOpen(false); }} onSubmit={(request) => { createMutation.mutate(request); }} />
    {editingProfile && <CreateLlmDialog mode="edit" profile={editingProfile} isOpen isSubmitting={updateMutation.isPending} error={updateMutation.error?.message ?? null} onClose={() => { if (!updateMutation.isPending) setEditingProfile(null); }} onSubmit={(request) => { updateMutation.mutate({ profileId: editingProfile.id, request }); }} />}
    <DeleteLlmDialog profile={deletingProfile} isDeleting={deleteMutation.isPending} error={deleteMutation.error?.message ?? null} onClose={() => { if (!deleteMutation.isPending) setDeletingProfile(null); }} onConfirm={() => { if (deletingProfile) deleteMutation.mutate(deletingProfile.id); }} />
  </div>;
}
