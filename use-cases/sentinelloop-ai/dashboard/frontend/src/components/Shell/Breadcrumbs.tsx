import { Link } from "react-router-dom";

import type { Crumb } from "./shellNav";

type Props = {
  items: Crumb[];
};

function looksLikeId(label: string): boolean {
  return /^(INC|EVT|QR|AUD|HK)-/i.test(label) || /^[A-Z]{2,}-\d/.test(label);
}

export function Breadcrumbs({ items }: Props) {
  if (!items.length) return null;
  return (
    <nav className="sl-breadcrumbs" aria-label="Breadcrumb">
      <ol>
        {items.map((item, index) => {
          const last = index === items.length - 1;
          const mono = last && looksLikeId(item.label);
          return (
            <li key={`${item.label}-${index}`}>
              {index > 0 ? <span className="sl-breadcrumbs__sep" aria-hidden="true">/</span> : null}
              {item.to && !last ? (
                <Link to={item.to}>{item.label}</Link>
              ) : (
                <span
                  aria-current={last ? "page" : undefined}
                  className={["sl-breadcrumbs__current", mono ? "ds-mono" : undefined].filter(Boolean).join(" ")}
                >
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
