import { useEffect, useRef } from "react";

import { FeatureGrid } from "./components/FeatureGrid";
import { Footer } from "./components/Footer";
import { Hero } from "./components/Hero";
import { NavBar } from "./components/NavBar";
import { PipelineSection } from "./components/PipelineSection";
import { ProblemSection } from "./components/ProblemSection";
import { TrustSection } from "./components/TrustSection";
import { LANDING_DESCRIPTION, LANDING_TITLE } from "./constants";
import { useLandingMotion } from "./useLandingMotion";
import "./landing.css";

export function LandingPage() {
  const rootRef = useRef<HTMLDivElement>(null);
  useLandingMotion(rootRef);

  useEffect(() => {
    const previousTitle = document.title;
    const meta = document.querySelector('meta[name="description"]');
    const previousDescription = meta?.getAttribute("content") ?? "";
    document.title = LANDING_TITLE;
    if (meta) meta.setAttribute("content", LANDING_DESCRIPTION);
    return () => {
      document.title = previousTitle;
      if (meta) meta.setAttribute("content", previousDescription);
    };
  }, []);

  return (
    <div className="sl-landing" id="top" ref={rootRef}>
      <a className="sl-skip" href="#main">
        Skip to content
      </a>
      <NavBar />
      <Hero />
      <main id="main">
        <ProblemSection />
        <PipelineSection />
        <FeatureGrid />
        <TrustSection />
      </main>
      <Footer />
    </div>
  );
}

export default LandingPage;
