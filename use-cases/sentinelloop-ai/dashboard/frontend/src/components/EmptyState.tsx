import type { ReactNode } from "react";

import { Button, Icon, type IconName } from "@ds/index";

type Props = {
  title: string;
  body: string;
  action?: string;
  onAction?: () => void;
  icon?: IconName;
  error?: boolean;
  children?: ReactNode;
};

export function EmptyState({ title, body, action, onAction, icon = "check", error = false, children }: Props) {
  return (
    <div className={error ? "ds-error-state" : "ds-empty-state"} role={error ? "alert" : "status"}>
      <Icon name={error ? "retry" : icon} width={28} height={28} />
      <h3>{title}</h3>
      <p>{body}</p>
      {action && onAction ? (
        <Button variant={error ? "primary" : "ghost"} onClick={onAction}>
          {action}
        </Button>
      ) : null}
      {children}
    </div>
  );
}
