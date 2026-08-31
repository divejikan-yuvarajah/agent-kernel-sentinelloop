import { useEffect, useState } from "react";

import { isDemoMode, setDemoMode, subscribeDemoMode } from "./demoMode";

export function useDemoMode(): [boolean, (next: boolean) => void] {
  const [enabled, setEnabled] = useState(isDemoMode);
  useEffect(() => subscribeDemoMode(() => setEnabled(isDemoMode())), []);
  return [enabled, setDemoMode];
}
