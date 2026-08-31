import type { HTMLAttributes, ReactNode } from "react";

type Props = HTMLAttributes<HTMLSpanElement> & { children: ReactNode };

export function Badge({ className = "", children, ...rest }: Props) {
  return (
    <span className={`ds-badge ${className}`.trim()} {...rest}>
      {children}
    </span>
  );
}
