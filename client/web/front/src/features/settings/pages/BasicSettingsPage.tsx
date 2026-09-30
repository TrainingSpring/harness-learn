import { FolderOpen, Laptop, Moon, Save, Sun } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Button } from "../../../components/Button";
import { getStorageSettings, updateStorageSettings } from "../api";
import { StorageDirectoryPicker } from "../components/StorageDirectoryPicker";
import type { Theme } from "../theme/ThemeProvider";
import { useTheme } from "../theme/ThemeProvider";

const options: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "跟随系统", icon: Laptop },
  { value: "light", label: "浅色", icon: Sun },
  { value: "dark", label: "深色", icon: Moon },
];

/** 浏览器主题和应用数据目录设置。 */
export function BasicSettingsPage() {
  const { theme, setTheme } = useTheme();
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);
  const [dataDir, setDataDir] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDirectoryPickerOpen, setIsDirectoryPickerOpen] = useState(false);

  useEffect(() => {
    let active = true;
    void getStorageSettings().then((settings) => {
      if (active) setDataDir(settings.dataDir);
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : "无法读取存储设置");
    });
    return () => { active = false; };
  }, []);

  const selectTheme = (index: number) => {
    const option = options[index];
    if (!option) return;
    setTheme(option.value);
    buttons.current[index]?.focus();
  };
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next = index;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % options.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (index - 1 + options.length) % options.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = options.length - 1;
    else return;
    event.preventDefault();
    selectTheme(next);
  };
  const saveStorage = async () => {
    if (!dataDir.trim()) return;
    setError(null); setStatus(null); setIsSaving(true);
    try {
      const settings = await updateStorageSettings({ dataDir: dataDir.trim() });
      setDataDir(settings.dataDir);
      setStatus(settings.restartRequired ? "已保存，重启服务后将迁移数据并生效。" : "已保存。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "存储设置保存失败");
    } finally {
      setIsSaving(false);
    }
  };

  return <div className="settings-section basic-settings"><div><h2>基础</h2><p>管理本机应用的显示和数据存储。</p></div>
    <section className="basic-settings__group" aria-labelledby="theme-title"><h3 id="theme-title">外观</h3><p>选择工作区的显示主题。</p><div className="segmented" role="radiogroup" aria-label="主题">{options.map(({ value, label, icon: Icon }, index) => <button ref={(element) => { buttons.current[index] = element; }} role="radio" aria-checked={theme === value} tabIndex={theme === value ? 0 : -1} className={theme === value ? "is-selected" : ""} key={value} onClick={() => setTheme(value)} onKeyDown={(event) => handleKeyDown(event, index)}><Icon size={16} />{label}</button>)}</div></section>
    <section className="basic-settings__group" aria-labelledby="storage-title"><h3 id="storage-title">存储</h3><p>角色、会话和上下文数据保存在此目录。更改后需重启服务。</p><label className="form-field"><span>存储目录</span><div className="form-field__input-action"><input value={dataDir} onChange={(event) => setDataDir(event.target.value)} placeholder="~/.harness/data" autoComplete="off" /><Button type="button" variant="ghost" aria-label="选择存储目录" title="选择存储目录" icon={<FolderOpen size={16} />} onClick={() => setIsDirectoryPickerOpen(true)} /></div></label><div className="basic-settings__actions"><Button variant="primary" icon={<Save size={16} />} disabled={isSaving || !dataDir.trim()} onClick={() => { void saveStorage(); }}>{isSaving ? "保存中" : "应用"}</Button>{status && <p className="form-notice" role="status">{status}</p>}</div>{error && <p className="inline-error" role="alert">{error}</p>}</section>
    {isDirectoryPickerOpen && <StorageDirectoryPicker selectedPath={dataDir} onClose={() => setIsDirectoryPickerOpen(false)} onSelect={(path) => { setDataDir(path); setIsDirectoryPickerOpen(false); }} />}
  </div>;
}
