import { Suspense } from "react";

import { DashboardConsole } from "@/components/dashboard/dashboard-console";

export default function DashboardPage() {
  return (
    <Suspense>
      <DashboardConsole />
    </Suspense>
  );
}
