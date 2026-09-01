import type { ReactNode } from "react";

import { Button } from "@ds/components/Button";

type Props = {
  title: string;
  detail?: string;
  onRetry?: () => void;
  action?: ReactNode;
};

export function ErrorState({ title, detail, onRetry, action }: Props) {
  return (
    <div className="sl-error-state" role="alert">
      <h2>{title}</h2>
      {detail ? <p>{detail}</p> : null}
      <div className="sl-error-state__actions">
        {onRetry ? <Button onClick={onRetry}>Retry</Button> : null}
        {action}
      </div>
    </div>
  );
}
