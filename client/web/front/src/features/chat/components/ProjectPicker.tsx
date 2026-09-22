import { useEffect, useState } from "react";
import { ArrowLeft, Check, Folder, LoaderCircle, X } from "lucide-react";
import type { ProjectDirectory } from "../../../api/types";
import { Button } from "../../../components/Button";
import { listProjectDirectories } from "../../sessions/api";

interface ProjectPickerProps {
  selectedPath: string | null;
  onSelect: (path: string | null) => void;
  onClose: () => void;
}

/** 仅允许浏览服务端 workspace 内目录的会话项目选择器。 */
export function ProjectPicker({ selectedPath, onSelect, onClose }: ProjectPickerProps) {
  const [currentPath, setCurrentPath] = useState(selectedPath ?? ".");
  const [directories, setDirectories] = useState<ProjectDirectory[]>([]);
  const [directoryName, setDirectoryName] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    void listProjectDirectories(currentPath)
      .then((result) => {
        if (cancelled) return;
        setCurrentPath(result.path);
        setDirectoryName(result.name);
        setDirectories(result.directories);
      })
      .catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "目录加载失败");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => { cancelled = true; };
  }, [currentPath]);

  const parentPath = currentPath === "." ? null : currentPath.split("/").slice(0, -1).join("/") || ".";

  return (
    <div className="dialog-backdrop" role="presentation">
      <div className="permission-dialog project-picker" role="dialog" aria-modal="true" aria-labelledby="project-picker-title">
        <div className="dialog-heading">
          <div><p className="eyebrow">会话环境</p><h2 id="project-picker-title">选择项目目录</h2></div>
          <Button variant="ghost" aria-label="关闭" icon={<X size={17} />} onClick={onClose} />
        </div>
        <div className="project-picker__path"><Folder size={15} /><code>{currentPath}</code></div>
        {isLoading && <p className="project-picker__state"><LoaderCircle className="spin" size={16} />正在读取目录</p>}
        {error && <p className="inline-error" role="alert">{error}</p>}
        {!isLoading && !error && (
          <div className="project-picker__list">
            {parentPath && <button type="button" className="project-picker__item" onClick={() => setCurrentPath(parentPath)}><ArrowLeft size={16} /><span>返回上级目录</span></button>}
            {directories.map((directory) => <button type="button" className="project-picker__item" key={directory.path} onClick={() => setCurrentPath(directory.path)}><Folder size={16} /><span>{directory.name}</span></button>)}
            {directories.length === 0 && !parentPath && <p className="project-picker__state">当前 workspace 没有可选子目录。</p>}
          </div>
        )}
        <div className="dialog-actions project-picker__actions">
          <Button type="button" onClick={() => { onSelect(null); onClose(); }}>不选择项目</Button>
          <Button type="button" variant="primary" icon={<Check size={16} />} onClick={() => { onSelect(currentPath); onClose(); }}>选择此目录</Button>
        </div>
      </div>
    </div>
  );
}
