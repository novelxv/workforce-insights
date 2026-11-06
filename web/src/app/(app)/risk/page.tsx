import type { Metadata } from "next";
import { Suspense } from "react";

import { RiskView } from "./view";

export const metadata: Metadata = { title: "Attrition risk" };

export default function RiskPage() {
  return (
    <Suspense>
      <RiskView />
    </Suspense>
  );
}
