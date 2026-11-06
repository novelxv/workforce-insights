import type { Metadata } from "next";
import { Suspense } from "react";

import { OverviewView } from "./overview-view";

export const metadata: Metadata = { title: "Overview" };

export default function OverviewPage() {
  return (
    <Suspense>
      <OverviewView />
    </Suspense>
  );
}
