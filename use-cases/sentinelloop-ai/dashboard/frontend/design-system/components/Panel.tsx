import type { HTMLAttributes, ReactNode } from "react";

type Props = HTMLAttributes<HTMLElement> & {
  title?: string;
  titleTooltip?: string;
  children: ReactNode;
};

export function Panel({ title, titleTooltip, className = "", children, ...rest }: Props) {
  return (
    <section className={`ds-panel ${className}`.trim()} {...rest}>
      {title ? (
        <h2 className="ds-panel__title" title={titleTooltip}>
          {title}
        </h2>
      ) : null}
      {children}
    </section>
  );
}
