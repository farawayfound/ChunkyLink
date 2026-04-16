import { createContext, useCallback, useContext, useRef, useState } from "react";

export type FlipDirection = "down" | "up";

interface PageTransitionCtx {
  flipping: boolean;
  flipDirection: FlipDirection;
  /** Call before navigating. Resolves when the flip-out half completes (~400ms). */
  startFlip: (direction: FlipDirection) => Promise<void>;
  /** Called by FlipTransition once the new page is fully revealed. */
  endFlip: () => void;
}

const Ctx = createContext<PageTransitionCtx>({
  flipping: false,
  flipDirection: "down",
  startFlip: async () => {},
  endFlip: () => {},
});

export function PageTransitionProvider({ children }: { children: React.ReactNode }) {
  const [flipping, setFlipping] = useState(false);
  const [flipDirection, setFlipDirection] = useState<FlipDirection>("down");
  const resolveRef = useRef<(() => void) | null>(null);

  const startFlip = useCallback((direction: FlipDirection): Promise<void> => {
    return new Promise((resolve) => {
      resolveRef.current = resolve;
      setFlipDirection(direction);
      setFlipping(true);
      // Resolve after the flip-out half so the route can change
      setTimeout(() => resolve(), 420);
    });
  }, []);

  const endFlip = useCallback(() => {
    setFlipping(false);
    resolveRef.current = null;
  }, []);

  return (
    <Ctx.Provider value={{ flipping, flipDirection, startFlip, endFlip }}>
      {children}
    </Ctx.Provider>
  );
}

export function usePageTransition() {
  return useContext(Ctx);
}
