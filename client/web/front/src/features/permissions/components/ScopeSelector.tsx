import type { PermissionScope } from "../../../api/types";

const labels: Record<PermissionScope, string> = {
  once: "仅本次",
  session: "当前会话",
  agent: "当前角色",
};

/** 仅展示服务端允许选择的权限范围。 */
export function ScopeSelector({ scopes, value, onChange }: { scopes: PermissionScope[]; value: PermissionScope; onChange: (scope: PermissionScope) => void }) {
  return (
    <fieldset className="scope-selector">
      <legend>允许范围</legend>
      {scopes.map((scope) => (
        <label key={scope}>
          <input type="radio" name="permission-scope" checked={value === scope} onChange={() => onChange(scope)} />
          <span>{labels[scope]}</span>
        </label>
      ))}
    </fieldset>
  );
}

export function scopeActionLabel(scope: PermissionScope): string {
  return scope === "once" ? "允许一次" : scope === "session" ? "本会话允许" : "该角色允许";
}
