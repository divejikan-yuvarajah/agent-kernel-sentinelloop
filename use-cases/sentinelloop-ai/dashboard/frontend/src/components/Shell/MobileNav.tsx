import { NavLink } from "react-router-dom";

import { SHELL_MOBILE_EXTRA, SHELL_PRIMARY_NAV } from "./shellNav";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function MobileNav({ open, onClose }: Props) {
  if (!open) return null;
  return (
    <div className="sl-mobile-nav" role="dialog" aria-modal="true" aria-label="Mobile menu">
      <button type="button" className="sl-mobile-nav__backdrop" aria-label="Close menu" onClick={onClose} />
      <nav className="sl-mobile-nav__panel">
        <p className="sl-mobile-nav__title">Menu</p>
        {[...SHELL_PRIMARY_NAV, ...SHELL_MOBILE_EXTRA].map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={"end" in link ? link.end : false}
            className={({ isActive }) => `sl-mobile-nav__link${isActive ? " is-active" : ""}`}
            onClick={onClose}
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
