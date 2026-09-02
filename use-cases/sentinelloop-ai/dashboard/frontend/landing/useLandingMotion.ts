import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useLayoutEffect, type RefObject } from "react";

import { usePrefersReducedMotion } from "./usePrefersReducedMotion";

gsap.registerPlugin(ScrollTrigger);

export function useLandingMotion(rootRef: RefObject<HTMLDivElement | null>) {
  const reduced = usePrefersReducedMotion();

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    if (reduced) {
      gsap.set(root.querySelectorAll("[data-reveal], .sl-hero__copy > *, .sl-loop-hero, .sl-nav"), {
        clearProps: "all",
        autoAlpha: 1,
      });
      return;
    }

    const ctx = gsap.context(() => {
      ScrollTrigger.defaults({ scroller: root });

      gsap.from(".sl-nav", { y: -20, autoAlpha: 0, duration: 0.55, ease: "power3.out" });

      const intro = gsap.timeline({ defaults: { ease: "power3.out" } });
      intro
        .from(".sl-hero__kicker", { y: 18, autoAlpha: 0, duration: 0.45 })
        .from(".sl-hero__headline", { y: 32, autoAlpha: 0, duration: 0.7 }, "-=0.2")
        .from(".sl-hero__lede", { y: 20, autoAlpha: 0, duration: 0.5 }, "-=0.35")
        .from(".sl-hero__actions > *", { y: 16, autoAlpha: 0, duration: 0.4, stagger: 0.07 }, "-=0.28")
        .from(".sl-hero__stats li", { y: 14, autoAlpha: 0, duration: 0.4, stagger: 0.08 }, "-=0.22")
        .from(".sl-loop-hero", { scale: 0.94, autoAlpha: 0, duration: 0.85, ease: "power3.out" }, 0.15);

      gsap.to(".sl-hero__orb", {
        y: 18,
        scale: 1.06,
        duration: 4.2,
        yoyo: true,
        repeat: -1,
        ease: "sine.inOut",
      });

      gsap.utils.toArray<HTMLElement>("[data-reveal]").forEach((el) => {
        gsap.fromTo(
          el,
          { y: 40, autoAlpha: 0 },
          {
            y: 0,
            autoAlpha: 1,
            duration: 0.75,
            ease: "power3.out",
            scrollTrigger: {
              trigger: el,
              start: "top 88%",
              once: true,
            },
          },
        );
      });
    }, root);

    const onResize = () => ScrollTrigger.refresh();
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      ctx.revert();
    };
  }, [reduced]);
}
