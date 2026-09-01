import { HOW_IT_WORKS } from "../constants";

export function PipelineSection() {
  return (
    <section className="sl-section sl-section--raised" id="how" aria-labelledby="how-title">
      <div className="sl-wrap">
        <p className="sl-kicker">Solution overview</p>
        <h2 id="how-title">How it works</h2>
        <p className="sl-section__lede">
          A worker message becomes a tracked case. AI understands it. Rules set risk. People act. The record stays.
        </p>
        <ol className="sl-steps">
          {HOW_IT_WORKS.map((step) => (
            <li key={step.title} className="sl-steps__item">
              <span className="sl-steps__dot" aria-hidden="true" />
              <h3>{step.title}</h3>
              <p>{step.description}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
