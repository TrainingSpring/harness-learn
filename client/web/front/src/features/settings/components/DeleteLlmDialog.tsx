import { AlertTriangle, Trash2, X } from "lucide-react";
import { Button } from "../../../components/Button";
import { useModalFocus } from "../../../hooks/useModalFocus";
import type { LLMProfileSummary } from "../../../api/types";

interface DeleteLlmDialogProps {
  profile: LLMProfileSummary | null;
  isDeleting: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: () => void;
}

/** 删除 LLM 配置前的显式确认弹窗，防止误删角色可用的模型连接。 */
export function DeleteLlmDialog({ profile, isDeleting, error, onClose, onConfirm }: DeleteLlmDialogProps) {
  const dialogRef = useModalFocus<HTMLDivElement>(profile !== null);

  if (profile === null) return null;

  return (
    <div className="dialog-backdrop">
      <div ref={dialogRef} className="permission-dialog delete-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-llm-title" tabIndex={-1}>
        <div className="dialog-heading">
          <div className="delete-dialog__title"><span className="delete-dialog__icon"><AlertTriangle size={19} /></span><div><p className="eyebrow">删除配置</p><h2 id="delete-llm-title">删除 {profile.name}</h2></div></div>
          <Button variant="ghost" aria-label="关闭" icon={<X size={17} />} onClick={onClose} disabled={isDeleting} />
        </div>
        <p>此操作会移除这套 LLM 连接配置，且无法撤销。仍被角色使用的配置无法删除。</p>
        {error && <p className="inline-error" role="alert">{error}</p>}
        <div className="dialog-actions"><Button type="button" onClick={onClose} disabled={isDeleting}>取消</Button><Button type="button" variant="danger" icon={<Trash2 size={16} />} onClick={onConfirm} disabled={isDeleting}>{isDeleting ? "删除中…" : "删除配置"}</Button></div>
      </div>
    </div>
  );
}
