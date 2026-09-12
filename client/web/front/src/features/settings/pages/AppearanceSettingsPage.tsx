import { Laptop, Moon, Sun } from "lucide-react";
import { useRef, type KeyboardEvent } from "react";
import type { Theme } from "../theme/ThemeProvider";
import { useTheme } from "../theme/ThemeProvider";

const options: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "跟随系统", icon: Laptop },
  { value: "light", label: "浅色", icon: Sun },
  { value: "dark", label: "深色", icon: Moon },
];

/** 浏览器本地主题设置。 */
export function AppearanceSettingsPage() {
  const { theme, setTheme } = useTheme();
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);
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
  return (
    <div className="settings-section"><div><h2>外观</h2><p>选择工作区的显示主题。</p></div>
      <div className="segmented" role="radiogroup" aria-label="主题">
        {options.map(({ value, label, icon: Icon }, index) => (
          <button
            ref={(element) => { buttons.current[index] = element; }}
            role="radio"
            aria-checked={theme === value}
            tabIndex={theme === value ? 0 : -1}
            className={theme === value ? "is-selected" : ""}
            key={value}
            onClick={() => setTheme(value)}
            onKeyDown={(event) => handleKeyDown(event, index)}
          ><Icon size={16} />{label}</button>
        ))}
      </div>
    </div>
  );
}
