import { useEffect, useId, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

type Props = {
  name: string;
  role: string;
};

export function UserMenu({ name, role }: Props) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const initials = name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onPointer);
    };
  }, [open]);

  return (
    <div className="sl-user" ref={rootRef}>
      <button
        type="button"
        className="sl-user__trigger"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="sl-user__mark" aria-hidden="true">
          {initials}
        </span>
        <span className="sl-user__copy">
          <strong>{role}</strong>
          <span className="sl-user__online">
            <span className="sl-user__dot" aria-hidden="true" />
            Online
          </span>
        </span>
      </button>
      {open ? (
        <div className="sl-user__menu" id={menuId} role="menu">
          <p>{name}</p>
          <Link to="/settings" role="menuitem" onClick={() => setOpen(false)}>
            Profile
          </Link>
          <Link to="/settings" role="menuitem" onClick={() => setOpen(false)}>
            Preferences
          </Link>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              navigate("/");
            }}
          >
            Logout
          </button>
        </div>
      ) : null}
    </div>
  );
}
