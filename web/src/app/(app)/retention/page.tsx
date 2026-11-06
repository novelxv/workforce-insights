import type { Metadata } from "next";
import { Suspense } from "react";

import { RetentionView } from "./view";

export const metadata: Metadata = { title: "Retention" };

export default function RetentionPage() {
  return (
    <Suspense>
      <RetentionView />
    </Suspense>
  );
}
