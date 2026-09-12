import type { ButtonHTMLAttributes, ReactNode } from "react";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  children: ReactNode;
}

/** 只显示图标的按钮，强制要求无障碍名称和原生 tooltip。 */
export function IconButton({ label, className = "", children, ...props }: IconButtonProps) {
  return (
    <button className={`icon-button ${className}`} aria-label={label} title={label} {...props}>
      {children}
    </button>
  );
}
