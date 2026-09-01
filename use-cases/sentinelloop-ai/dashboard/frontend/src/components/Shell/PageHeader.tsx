import type { ReactNode } from "react";

import { Breadcrumbs } from "./Breadcrumbs";
import type { Crumb } from "./shellNav";

type Props = {
  title: string;
  description?: string;
  actions?: ReactNode;
  breadcrumbs?: Crumb[];
};

export function PageHeader({ title, description, actions, breadcrumbs }: Props) {
  return (
    <header className="sl-page-header">
      {breadcrumbs ? <Breadcrumbs items={breadcrumbs} /> : null}
      <div className="sl-page-header__row">
        <div>
          <h1 className="sl-page-header__title">{title}</h1>
          {description ? <p className="sl-page-header__desc">{description}</p> : null}
        </div>
        {actions ? <div className="sl-page-header__actions">{actions}</div> : null}
      </div>
    </header>
  );
}
