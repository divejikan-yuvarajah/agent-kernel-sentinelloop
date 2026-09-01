import { Badge, Icon } from "@ds/index";

import { FEATURES } from "../constants";

export function FeatureGrid() {
  return (
    <section className="sl-section" id="features" aria-labelledby="features-title">
      <div className="sl-wrap">
        <p className="sl-kicker">Distinguishing features</p>
        <h2 id="features-title">Built for the floor, not the demo reel</h2>
        <p className="sl-section__lede">
          QR context, duplicate merge, audit export, emergency bypass, prediction, vision, voice, shift handover,
          and manual dashboard entry — each one removes a reporting or accountability failure.
        </p>
        <ul className="sl-features">
          {FEATURES.map((feature) => (
            <li key={feature.title}>
              <article className="sl-feature">
                <Icon name={feature.icon} />
                {feature.badge ? <Badge className="sl-feature__badge">{feature.badge}</Badge> : null}
                <h3>{feature.title}</h3>
                <p>{feature.description}</p>
              </article>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
