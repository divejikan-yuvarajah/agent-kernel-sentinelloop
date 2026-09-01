import { useEffect, useState } from "react";

import { canLogHazard, readOperatorRole, subscribeOperatorRole, type OperatorRole } from "../demo/operatorRole";

export function useOperatorRole() {
  const [role, setRole] = useState<OperatorRole>(readOperatorRole);
  useEffect(() => subscribeOperatorRole(() => setRole(readOperatorRole())), []);
  return { role, canCreate: canLogHazard(role) };
}
