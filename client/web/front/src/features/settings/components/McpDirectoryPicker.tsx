import { useEffect, useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, Check, Folder, LoaderCircle, X } from "lucide-react";
import { Button } from "../../../components/Button";
import { listMcpDirectories } from "../api";

interface Props {
  selectedPath: string | null;
  onSelect: (path: string | null) => void;
  onClose: () => void;
}

/** 选择 MCP 服务所在目录；目录只属于 MCP 配置，不会改变 Session workspace。 */
export function McpDirectoryPicker({ selectedPath, onSelect, onClose }: Props) {
  const [currentPath, setCurrentPath] = useState(selectedPath ?? ".");
  const [inputPath, setInputPath] = useState(selectedPath ?? "");
  const [directories, setDirectories] = useState<{ path: string; name: string }[]>([]);
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    void listMcpDirectories(currentPath).then((result) => {
      if (cancelled) return;
      setCurrentPath(result.path); setInputPath(result.path); setParentPath(result.parentPath); setDirectories(result.directories);
    }).catch((cause) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : "目录加载失败");
    }).finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [currentPath]);

  const navigateToInput = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const path = inputPath.trim();
    if (path && path !== currentPath) setCurrentPath(path);
  };

  return <div className="dialog-backdrop" role="presentation"><div className="permission-dialog project-picker" role="dialog" aria-modal="true" aria-labelledby="mcp-directory-picker-title">
    <div className="dialog-heading"><div><h2 id="mcp-directory-picker-title">选择 MCP 服务目录</h2></div><Button variant="ghost" aria-label="关闭" icon={<X size={17} />} onClick={onClose} /></div>
    <form className="project-picker__path-form" onSubmit={navigateToInput}><label htmlFor="mcp-directory-path">目录路径</label><div className="project-picker__path-control"><Folder size={15} aria-hidden="true" /><input id="mcp-directory-path" value={inputPath} onChange={(event) => setInputPath(event.target.value)} placeholder="输入 MCP 服务目录路径" autoComplete="off" /><Button type="submit" variant="ghost" icon={<ArrowRight size={15} />} disabled={isLoading || !inputPath.trim()}>前往</Button></div></form>
    {isLoading && <p className="project-picker__state"><LoaderCircle className="spin" size={16} />正在读取目录</p>}{error && <p className="inline-error" role="alert">{error}</p>}
    {!isLoading && !error && <div className="project-picker__list">{parentPath && <button type="button" className="project-picker__item" aria-label="返回上级目录" onClick={() => setCurrentPath(parentPath)}><ArrowLeft size={16} aria-hidden="true" /><span>..</span></button>}{directories.map((directory) => <button type="button" className="project-picker__item" key={directory.path} onClick={() => setCurrentPath(directory.path)}><Folder size={16} aria-hidden="true" /><span>{directory.name}</span></button>)}{directories.length === 0 && <p className="project-picker__state">当前目录没有可选子目录。</p>}</div>}
    <div className="dialog-actions project-picker__actions"><Button type="button" onClick={onClose}>取消</Button><Button type="button" variant="primary" icon={<Check size={16} />} onClick={() => onSelect(currentPath)}>选择此目录</Button></div>
  </div></div>;
}
