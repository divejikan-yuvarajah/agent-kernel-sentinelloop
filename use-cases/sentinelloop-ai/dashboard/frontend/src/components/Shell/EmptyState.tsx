import type { ReactNode } from "react";

type Props = {
  title: string;
  detail?: string;
  action?: ReactNode;
};

export function EmptyState({ title, detail, action }: Props) {
  return (
    <div className="sl-empty-state" role="status">
      <h2>{title}</h2>
      {detail ? <p>{detail}</p> : null}
      {action ? <div className="sl-empty-state__action">{action}</div> : null}
    </div>
  );
}
