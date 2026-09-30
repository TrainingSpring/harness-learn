import { Check, Folder, FolderUp, LoaderCircle, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Button } from "../../../components/Button";
import { useModalFocus } from "../../../hooks/useModalFocus";
import { listStorageDirectories } from "../api";

interface StorageDirectoryPickerProps {
  selectedPath: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}

/** 浏览并选择应用数据存储目录，不影响任何会话的项目工作目录。 */
export function StorageDirectoryPicker({ selectedPath, onSelect, onClose }: StorageDirectoryPickerProps) {
  const dialogRef = useModalFocus<HTMLDivElement>();
  const [currentPath, setCurrentPath] = useState(selectedPath || ".");
  const [inputPath, setInputPath] = useState(selectedPath || ".");
  const [directories, setDirectories] = useState<Array<{ path: string; name: string }>>([]);
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    void listStorageDirectories(currentPath)
      .then((result) => {
        if (cancelled) return;
        setCurrentPath(result.path);
        setInputPath(result.path);
        setParentPath(result.parentPath);
        setDirectories(result.directories);
      })
      .catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "目录加载失败");
      })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [currentPath]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const navigateToInput = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextPath = inputPath.trim();
    if (nextPath && nextPath !== currentPath) setCurrentPath(nextPath);
  };

  return (
    <div className="dialog-backdrop" role="presentation">
      <div ref={dialogRef} className="permission-dialog project-picker" role="dialog" aria-modal="true" aria-labelledby="storage-directory-picker-title" tabIndex={-1}>
        <div className="dialog-heading">
          <div><h2 id="storage-directory-picker-title">选择存储目录</h2></div>
          <Button variant="ghost" aria-label="关闭目录选择" title="关闭" icon={<X size={17} />} onClick={onClose} />
        </div>
        <form className="project-picker__path-form" onSubmit={navigateToInput}>
          <label htmlFor="storage-directory-path">目录路径</label>
          <div className="project-picker__path-control">
            <Folder size={15} aria-hidden="true" />
            <input id="storage-directory-path" value={inputPath} onChange={(event) => setInputPath(event.target.value)} placeholder="输入存储目录路径" autoComplete="off" />
            <Button type="submit" variant="ghost" disabled={isLoading || !inputPath.trim()}>前往</Button>
          </div>
        </form>
        {isLoading && <p className="project-picker__state"><LoaderCircle className="spin" size={16} />正在读取目录</p>}
        {error && <p className="inline-error" role="alert">{error}</p>}
        {!isLoading && !error && (
          <div className="project-picker__list">
            {parentPath && <button type="button" className="project-picker__item" aria-label="返回上级目录" onClick={() => setCurrentPath(parentPath)}><FolderUp size={16} aria-hidden="true" /><span>..</span></button>}
            {directories.map((directory) => <button type="button" className="project-picker__item" key={directory.path} onClick={() => setCurrentPath(directory.path)}><Folder size={16} aria-hidden="true" /><span>{directory.name}</span></button>)}
            {directories.length === 0 && <p className="project-picker__state">当前目录没有子目录。</p>}
          </div>
        )}
        <div className="dialog-actions project-picker__actions">
          <Button type="button" onClick={onClose}>取消</Button>
          <Button type="button" variant="primary" icon={<Check size={16} />} disabled={isLoading || Boolean(error)} onClick={() => onSelect(currentPath)}>选择此目录</Button>
        </div>
      </div>
    </div>
  );
}
