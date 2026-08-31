import { useState } from "react";

type Props = {
  src?: string | null;
  alt: string;
  className?: string;
  ratio?: "4/3" | "1/1" | "16/9";
};

export function EvidenceImage({ src, alt, className = "", ratio = "4/3" }: Props) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  if (!src || failed) {
    return (
      <div className={`ds-photo ds-photo--empty ${className}`} data-ratio={ratio} role="img" aria-label="No Evidence Available">
        <span>No Evidence Available</span>
      </div>
    );
  }
  return (
    <div className={`ds-photo ${loaded ? "ds-photo--ready" : "ds-photo--pending"} ${className}`} data-ratio={ratio}>
      {!loaded ? <span className="ds-photo__skeleton" aria-hidden="true" /> : null}
      <img
        src={src}
        alt={alt}
        loading="lazy"
        decoding="async"
        onLoad={() => setLoaded(true)}
        onError={() => setFailed(true)}
      />
    </div>
  );
}
