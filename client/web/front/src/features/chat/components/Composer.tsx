import { useEffect, useRef, useState, type CompositionEvent, type KeyboardEvent } from "react";
import { ArrowUp, ChevronDown, Folder, Lock, Square } from "lucide-react";
import type { PermissionMode } from "../../../api/types";
import { IconButton } from "../../../components/IconButton";
import { ProjectPicker } from "./ProjectPicker";

interface ComposerProps {
  onSend: (text: string) => void;
  isRunning: boolean;
  onStop: () => void;
  placeholder?: string;
  autoFocus?: boolean;
  projectPath?: string | null;
  isProjectLocked?: boolean;
  permissionMode?: PermissionMode;
  onProjectChange?: (path: string | null) => void;
  onPermissionModeChange?: (mode: PermissionMode) => void;
  showProjectSelection?: boolean;
}

/** 对话输入器，处理自动增高、中文输入法组合和 Enter 发送语义。 */
export function Composer({ onSend, isRunning, onStop, placeholder = "输入消息…", autoFocus = false, projectPath = null, isProjectLocked = false, permissionMode = "plan", onProjectChange = () => undefined, onPermissionModeChange = () => undefined, showProjectSelection = true }: ComposerProps) {
  const [value, setValue] = useState("");
  const composing = useRef(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const [showProjectPicker, setShowProjectPicker] = useState(false);

  useEffect(() => {
    const element = textarea.current;
    if (!element) return;
    element.style.height = "0px";
    element.style.height = `${Math.min(element.scrollHeight, 176)}px`;
  }, [value]);

  const submit = () => {
    const text = value.trim();
    if (!text || isRunning) return;
    onSend(text);
    setValue("");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !composing.current && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="composer">
      <div className="composer__toolbar">
        {showProjectSelection && <button type="button" className="composer__project" aria-label={isProjectLocked ? "项目目录已锁定" : "选择项目目录"} disabled={isRunning || isProjectLocked} onClick={() => setShowProjectPicker(true)} title={isProjectLocked ? "项目目录已锁定" : "选择项目目录"}>
          {isProjectLocked ? <Lock size={15} /> : <Folder size={15} />}
          <span>{projectPath ?? "空项目"}</span>
        </button>}
        <label className="composer__mode" title="会话权限模式">
          <span className="sr-only">权限模式</span>
          <select aria-label="权限模式" disabled={isRunning} value={permissionMode} onChange={(event) => onPermissionModeChange(event.target.value as PermissionMode)}>
            <option value="plan">PLAN · 规划</option>
            <option value="build">BUILD · 执行前确认</option>
            <option value="yolo">YOLO · 自动执行</option>
          </select>
          <ChevronDown size={14} />
        </label>
      </div>
      <textarea
        ref={textarea}
        aria-label="消息"
        autoFocus={autoFocus}
        disabled={isRunning}
        placeholder={placeholder}
        rows={1}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onCompositionStart={() => { composing.current = true; }}
        onCompositionEnd={(_event: CompositionEvent) => { composing.current = false; }}
        onKeyDown={handleKeyDown}
      />
      {isRunning ? (
        <IconButton label="停止生成" className="composer__submit" onClick={onStop}><Square size={15} fill="currentColor" /></IconButton>
      ) : (
        <IconButton label="发送消息" className="composer__submit" disabled={!value.trim()} onClick={submit}><ArrowUp size={18} /></IconButton>
      )}
      {showProjectPicker && <ProjectPicker selectedPath={projectPath} onSelect={onProjectChange} onClose={() => setShowProjectPicker(false)} />}
    </div>
  );
}
