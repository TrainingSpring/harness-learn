import { Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "../../../components/Button";
import { useModalFocus } from "../../../hooks/useModalFocus";
import type { SkillSummary } from "../../../api/types";

interface SkillPickerDialogProps {
  isOpen: boolean;
  skills: SkillSummary[];
  selectedSkillIds: string[];
  onClose: () => void;
  onConfirm: (skillIds: string[]) => void;
}

/** 在独立弹窗中选择角色 Skills，避免大量 Skill 撑开角色表单。 */
export function SkillPickerDialog({
  isOpen,
  skills,
  selectedSkillIds,
  onClose,
  onConfirm,
}: SkillPickerDialogProps) {
  const dialogRef = useModalFocus<HTMLDivElement>(isOpen);
  const [draftIds, setDraftIds] = useState<string[]>(selectedSkillIds);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!isOpen) return;
    setDraftIds(selectedSkillIds);
    setQuery("");
  }, [isOpen, selectedSkillIds]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const filteredSkills = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    if (!normalizedQuery) return skills;
    return skills.filter((skill) => `${skill.name} ${skill.description}`.toLocaleLowerCase().includes(normalizedQuery));
  }, [query, skills]);

  if (!isOpen) return null;

  const toggleSkill = (skillId: string) => {
    setDraftIds((current) => current.includes(skillId)
      ? current.filter((id) => id !== skillId)
      : [...current, skillId]);
  };

  const selectVisible = () => {
    setDraftIds((current) => [...current, ...filteredSkills.map((skill) => skill.id).filter((id) => !current.includes(id))]);
  };

  const clearVisible = () => {
    const visibleIds = new Set(filteredSkills.map((skill) => skill.id));
    setDraftIds((current) => current.filter((id) => !visibleIds.has(id)));
  };

  return (
    <div className="dialog-backdrop skill-picker-backdrop">
      <div
        ref={dialogRef}
        className="permission-dialog skill-picker-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="skill-picker-title"
        tabIndex={-1}
      >
        <div className="dialog-heading">
          <div>
            <p className="eyebrow">角色配置</p>
            <h2 id="skill-picker-title">选择 Skills</h2>
          </div>
          <Button variant="ghost" aria-label="关闭 Skill 选择" icon={<X size={17} />} onClick={onClose} />
        </div>
        <div className="skill-picker-toolbar">
          <label className="skill-picker-search">
            <Search size={16} aria-hidden="true" />
            <input aria-label="搜索 Skills" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称或描述" autoFocus />
          </label>
          <span className="skill-picker-count">已选择 {draftIds.length} 个</span>
        </div>
        <div className="skill-picker-actions">
          <Button type="button" onClick={selectVisible}>选择当前结果</Button>
          <Button type="button" onClick={clearVisible}>清除当前结果</Button>
        </div>
        <div className="skill-picker-list" role="group" aria-label="Skills 列表">
          {filteredSkills.length === 0 && <p className="form-hint">没有匹配的 Skill。</p>}
          {filteredSkills.map((skill) => (
            <label className="skill-picker-option" key={skill.id}>
              <input aria-label={skill.name} type="checkbox" checked={draftIds.includes(skill.id)} disabled={skill.status !== "AVAILABLE" && !draftIds.includes(skill.id)} onChange={() => toggleSkill(skill.id)} />
              <span className="skill-picker-option__content"><strong>{skill.name}</strong><small>{skill.description || "暂无描述"}</small></span>
              {skill.status !== "AVAILABLE" && <span className="status status--muted">{skill.status === "MISSING" ? "缺失" : "无效"}</span>}
            </label>
          ))}
        </div>
        <div className="dialog-actions">
          <Button type="button" onClick={onClose}>取消</Button>
          <Button type="button" variant="primary" onClick={() => { onConfirm(draftIds); onClose(); }}>确认选择</Button>
        </div>
      </div>
    </div>
  );
}
