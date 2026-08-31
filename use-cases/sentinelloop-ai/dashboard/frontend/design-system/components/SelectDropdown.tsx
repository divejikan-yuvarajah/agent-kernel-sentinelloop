import type { SelectHTMLAttributes } from "react";

type Option = { value: string; label: string };

type Props = SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  options: Option[];
};

export function SelectDropdown({ label, id, options, className = "", ...rest }: Props) {
  const selectId = id ?? rest.name ?? "select";
  return (
    <label className={`ds-field ${className}`.trim()} htmlFor={selectId}>
      <span className="ds-field__label">{label}</span>
      <select id={selectId} className="ds-select" {...rest}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
