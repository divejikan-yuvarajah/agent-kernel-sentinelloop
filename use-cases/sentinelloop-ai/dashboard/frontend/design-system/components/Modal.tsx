import { useEffect, type ReactNode } from "react";

type Props = {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  className?: string;
};

export function Modal({ open, title, onClose, children, className = "" }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="ds-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className={`ds-modal ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ds-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="ds-modal-title" className="ds-modal__title">
          {title}
        </h2>
        {children}
      </div>
    </div>
  );
}
