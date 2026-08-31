import type { ReactNode } from "react";

type Props = {
  timestamp: string;
  title: string;
  children?: ReactNode;
};

export function TimelineItem({ timestamp, title, children }: Props) {
  return (
    <li className="ds-timeline__item">
      <time className="ds-timeline__time" dateTime={timestamp}>
        {timestamp}
      </time>
      <p className="ds-timeline__title">{title}</p>
      {children ? <div className="ds-timeline__body">{children}</div> : null}
    </li>
  );
}
