import { useRef, useState } from "react";
import { BookOpen, CheckCircle2, CircleAlert, FileUp, RefreshCw } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "../../../components/Button";
import { IconButton } from "../../../components/IconButton";
import { EmptyState } from "../../../components/EmptyState";
import { ErrorState } from "../../../components/ErrorState";
import { Skeleton } from "../../../components/Skeleton";
import { importSkill, listSkills, refreshSkills } from "../api";
import type { SkillStatus, SkillSummary } from "../../../api/types";

const statusLabels: Record<SkillStatus, string> = {
  AVAILABLE: "可用",
  INVALID: "格式错误",
  MISSING: "目录缺失",
};

function StatusIcon({ status }: { status: SkillStatus }) {
  return status === "AVAILABLE"
    ? <CheckCircle2 size={15} aria-hidden="true" />
    : <CircleAlert size={15} aria-hidden="true" />;
}

function SkillRow({ skill }: { skill: SkillSummary }) {
  return (
    <article className="skill-row">
      <div className="skill-row__identity">
        <span className={`skill-row__icon skill-row__icon--${skill.status.toLowerCase()}`}><BookOpen size={16} /></span>
        <div>
          <h3>{skill.name}</h3>
          <p>{skill.description}</p>
          {skill.validationError && <small className="skill-row__error">{skill.validationError}</small>}
        </div>
      </div>
      <div className="skill-row__meta">
        <span className={`status status--${skill.status.toLowerCase()}`}><StatusIcon status={skill.status} />{statusLabels[skill.status]}</span>
        <span>{skill.agentCount} 个角色使用</span>
      </div>
    </article>
  );
}

export function SkillSettingsPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const skills = useQuery({ queryKey: ["skills"], queryFn: listSkills });
  const refresh = useMutation({
    mutationFn: refreshSkills,
    onSuccess: async (result) => {
      setNotice(`新增 ${result.added}，更新 ${result.updated}，未变化 ${result.unchanged}，缺失 ${result.missing}，无效 ${result.invalid}`);
      await skills.refetch();
    },
  });
  const importMutation = useMutation({
    mutationFn: importSkill,
    onSuccess: async (result) => {
      setNotice(`导入完成，新增 ${result.added}，更新 ${result.updated}`);
      await skills.refetch();
    },
  });

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) importMutation.mutate(file);
  };

  return (
    <div className="settings-section">
      <div className="settings-section__header">
        <div><h2>Skills</h2><p>从本地 Skill 目录同步可分配给角色的指令和参考资料。</p></div>
        <div className="settings-section__actions">
          <input ref={fileInputRef} type="file" accept=".zip,application/zip" hidden onChange={handleFileChange} />
          <Button icon={<FileUp size={16} />} onClick={() => fileInputRef.current?.click()} disabled={importMutation.isPending || refresh.isPending}>新增 Skill</Button>
          <IconButton label="刷新 Skills" onClick={() => { setNotice(null); refresh.mutate(); }} disabled={refresh.isPending || importMutation.isPending}>
            <RefreshCw size={17} className={refresh.isPending ? "spin" : undefined} />
          </IconButton>
        </div>
      </div>
      {notice && <p className="form-notice" role="status">{notice}</p>}
      {refresh.error && <p className="inline-error" role="alert">{refresh.error.message}</p>}
      {importMutation.error && <p className="inline-error" role="alert">{importMutation.error.message}</p>}
      {skills.isLoading && <Skeleton rows={4} />}
      {skills.isError && <ErrorState message={skills.error.message} onRetry={() => { void skills.refetch(); }} />}
      {skills.data?.items.length === 0 && <EmptyState icon={<BookOpen />} title="尚未发现 Skill" description="将包含 SKILL.md 的目录放入固定 Skills 目录后点击刷新，或导入 ZIP 文件。" />}
      {skills.data && skills.data.items.length > 0 && <div className="skill-list" role="list">{skills.data.items.map((skill) => <SkillRow key={skill.id} skill={skill} />)}</div>}
    </div>
  );
}
