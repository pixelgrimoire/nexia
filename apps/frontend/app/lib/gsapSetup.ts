"use client";

import { gsap } from "gsap";
import { useGSAP } from "@gsap/react";

let registered = false;

export function setupGSAP() {
  if (registered || typeof window === "undefined") return gsap;
  try {
    // Always register the React plugin
    gsap.registerPlugin(useGSAP as any);
  } catch {}

  // Try to register commonly used core plugins (non-club) first
  Promise.all([
    import("gsap/Draggable").catch(() => null),
    import("gsap/Flip").catch(() => null),
    import("gsap/MotionPathPlugin").catch(() => null),
    import("gsap/Observer").catch(() => null),
    import("gsap/ScrollTrigger").catch(() => null),
    import("gsap/ScrollToPlugin").catch(() => null),
    import("gsap/TextPlugin").catch(() => null),
  ]).then((mods) => {
    try {
      gsap.registerPlugin(
        ...mods.filter(Boolean).map((m: any) => m?.default || Object.values(m || {})[0]).filter(Boolean)
      );
    } catch {}
  });

  // Attempt to load bonus plugins if available; ignore on failure
  Promise.all([
    import("gsap/EasePack").catch(() => null),
    import("gsap/CustomEase").catch(() => null),
    import("gsap/CustomBounce").catch(() => null),
    import("gsap/CustomWiggle").catch(() => null),
    import("gsap/DrawSVGPlugin").catch(() => null),
    import("gsap/EaselPlugin").catch(() => null),
    import("gsap/GSDevTools").catch(() => null),
    import("gsap/InertiaPlugin").catch(() => null),
    import("gsap/MotionPathHelper").catch(() => null),
    import("gsap/MorphSVGPlugin").catch(() => null),
    import("gsap/Physics2DPlugin").catch(() => null),
    import("gsap/PhysicsPropsPlugin").catch(() => null),
    import("gsap/PixiPlugin").catch(() => null),
    import("gsap/ScrambleTextPlugin").catch(() => null),
    import("gsap/ScrollSmoother").catch(() => null),
    import("gsap/SplitText").catch(() => null),
  ]).then((mods) => {
    try {
      gsap.registerPlugin(
        ...mods.filter(Boolean).map((m: any) => m?.default || Object.values(m || {})[0]).filter(Boolean)
      );
    } catch {}
  });

  registered = true;
  return gsap;
}

export { gsap };

