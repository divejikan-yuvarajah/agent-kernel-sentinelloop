import { TRUST_PILLARS } from "../constants";

export function TrustSection() {
  return (
    <section className="sl-section sl-section--raised" id="trust" aria-labelledby="trust-title">
      <div className="sl-wrap">
        <p className="sl-kicker" data-reveal>
          Trust engineering
        </p>
        <h2 id="trust-title" data-reveal>
          Built to be trusted,
          <br />
          not just built to look smart.
        </h2>
        <p className="sl-section__lede" data-reveal>
          SentinelLoop’s agent pipeline handles the understanding and the judgment. Rules, spend caps, and a person on
          the floor still make the safety-critical calls.
        </p>
        <ul className="sl-pillars" data-reveal>
          {TRUST_PILLARS.map((pillar) => (
            <li key={pillar.title}>
              <article className="sl-pillar">
                <h3>{pillar.title}</h3>
                <p>{pillar.description}</p>
              </article>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
