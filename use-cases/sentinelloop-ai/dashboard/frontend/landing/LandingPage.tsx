import { useEffect } from "react";

import { FeatureGrid } from "./components/FeatureGrid";
import { Footer } from "./components/Footer";
import { Hero } from "./components/Hero";
import { PipelineSection } from "./components/PipelineSection";
import { ProblemSection } from "./components/ProblemSection";
import { TrustSection } from "./components/TrustSection";
import { LANDING_DESCRIPTION, LANDING_TITLE } from "./constants";
import "./landing.css";

export function LandingPage() {
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
    <div className="sl-landing" id="top">
      <a className="sl-skip" href="#main">
        Skip to content
      </a>
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
