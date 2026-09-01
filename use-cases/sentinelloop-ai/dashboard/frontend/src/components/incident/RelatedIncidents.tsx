import { Link } from "react-router-dom";

import { Panel } from "@ds/index";

type Related = {
  incident_id: string;
  title?: string | null;
  status?: string | null;
  similarity_score?: number | null;
};

type Props = {
  category: string | null;
  items: Related[];
};

export function RelatedIncidents({ category, items }: Props) {
  return (
    <Panel title={`Related ${category || "Hazard"} Reports`} className="ii-related">
      {items.length === 0 ? (
        <p className="ds-empty">No related incidents on record</p>
      ) : (
        <ul className="ii-related__list">
          {items.map((item) => (
            <li key={item.incident_id}>
              <Link to={`/incidents/${encodeURIComponent(item.incident_id)}`} className="ds-mono">
                {item.incident_id}
              </Link>
              <span>{item.title || item.status || "Related case"}</span>
              {item.similarity_score != null ? (
                <span className="ds-mono">similarity {Math.round(item.similarity_score * 100)}%</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
