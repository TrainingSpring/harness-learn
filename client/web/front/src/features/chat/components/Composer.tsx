import { useEffect, useRef, useState, type CompositionEvent, type KeyboardEvent } from "react";
import { ArrowUp, Square } from "lucide-react";
import { IconButton } from "../../../components/IconButton";

interface ComposerProps {
  onSend: (text: string) => void;
  isRunning: boolean;
  onStop: () => void;
  placeholder?: string;
  autoFocus?: boolean;
}

/** 对话输入器，处理自动增高、中文输入法组合和 Enter 发送语义。 */
export function Composer({ onSend, isRunning, onStop, placeholder = "输入消息…", autoFocus = false }: ComposerProps) {
  const [value, setValue] = useState("");
  const composing = useRef(false);
  const textarea = useRef<HTMLTextAreaElement>(null);

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
    </div>
  );
}
