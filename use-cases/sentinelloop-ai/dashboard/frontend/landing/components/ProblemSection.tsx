import { Icon } from "@ds/index";

import { PROBLEMS } from "../constants";

export function ProblemSection() {
  return (
    <section className="sl-section" id="why" aria-labelledby="why-title">
      <div className="sl-wrap">
        <p className="sl-kicker" data-reveal>
          Problem statement
        </p>
        <h2 id="why-title" data-reveal>
          Why this exists
        </h2>
        <p className="sl-section__lede" data-reveal>
          Workplaces regularly have warning signs before an accident — exposed wiring, chemical spills, damaged
          machinery, blocked exits — that go unreported or unresolved.
        </p>
        <ul className="sl-timeline" data-reveal>
          {PROBLEMS.map((problem) => (
            <li key={problem.title}>
              <span className="sl-timeline__mark" aria-hidden="true">
                <Icon name={problem.icon} />
              </span>
              <div>
                <h3>{problem.title}</h3>
                <p>{problem.description}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
