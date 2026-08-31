import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "quiet";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  children: ReactNode;
};

export function Button({ variant = "primary", className = "", children, type = "button", ...rest }: Props) {
  const extra = variant === "primary" ? "" : ` ds-btn--${variant}`;
  return (
    <button type={type} className={`ds-btn${extra} ${className}`.trim()} {...rest}>
      {children}
    </button>
  );
}
