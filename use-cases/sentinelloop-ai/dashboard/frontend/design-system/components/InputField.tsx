import type { InputHTMLAttributes } from "react";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
};

export function InputField({ label, id, className = "", ...rest }: Props) {
  const inputId = id ?? rest.name ?? "field";
  return (
    <label className={`ds-field ${className}`.trim()} htmlFor={inputId}>
      <span className="ds-field__label">{label}</span>
      <input id={inputId} className="ds-input" {...rest} />
    </label>
  );
}
