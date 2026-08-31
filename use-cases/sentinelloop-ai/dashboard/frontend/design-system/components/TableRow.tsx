import type { ReactNode, TdHTMLAttributes } from "react";

type Props = {
  cells: ReactNode[];
  cellProps?: TdHTMLAttributes<HTMLTableCellElement>[];
};

export function TableRow({ cells, cellProps = [] }: Props) {
  return (
    <tr className="ds-row">
      {cells.map((cell, index) => (
        <td key={index} {...cellProps[index]}>
          {cell}
        </td>
      ))}
    </tr>
  );
}
