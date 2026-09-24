import { ShieldAlert } from "lucide-react";
import type { PermissionDecision, PermissionRequest, PermissionScope } from "../../../api/types";
import { Button } from "../../../components/Button";
import { useModalFocus } from "../../../hooks/useModalFocus";

interface PermissionDialogProps {
  request: PermissionRequest;
  isSubmitting: boolean;
  onDecision: (decision: PermissionDecision, scope: PermissionScope) => void;
}

/**
 * Runtime 暂停时的强制决策界面。它没有关闭按钮，避免关闭弹窗被误解为允许；
 * 用户必须明确拒绝或选择一个服务端允许的范围。
 */
export function PermissionDialog({ request, isSubmitting, onDecision }: PermissionDialogProps) {
  const dialog = useModalFocus<HTMLDivElement>();
  const canPersist = request.allowedScopes.includes("session");

  return (
    <div className="dialog-backdrop">
      <div ref={dialog} className="permission-dialog" role="dialog" aria-modal="true" aria-labelledby="permission-title" tabIndex={-1}>
        <div className="permission-dialog__heading">
          <span className="permission-dialog__icon"><ShieldAlert size={20} /></span>
          <div>
            <p className="eyebrow">需要你的确认</p>
            <h2 id="permission-title">{request.toolName} 请求执行操作</h2>
          </div>
        </div>
        <dl className="permission-dialog__details">
          <div><dt>权限动作</dt><dd>{request.action}</dd></div>
          <div><dt>目标资源</dt><dd><code>{request.resource ?? "无特定资源"}</code></dd></div>
        </dl>
        {request.toolName === "bash" && <p className="form-hint">此处确认的是整条终端命令。本会话允许或不再询问会影响后续所有终端命令。</p>}
        <div className="permission-dialog__actions">
          <Button variant="primary" disabled={isSubmitting} onClick={() => onDecision("allow", "once")}>仅本次允许</Button>
          {canPersist && <Button variant="primary" disabled={isSubmitting} onClick={() => onDecision("allow", "session")}>本会话允许</Button>}
          <Button disabled={isSubmitting} onClick={() => onDecision("deny", "once")}>拒绝</Button>
          {canPersist && <Button disabled={isSubmitting} onClick={() => onDecision("deny", "session")}>不再询问</Button>}
        </div>
      </div>
    </div>
  );
}
