import type { Metadata } from "next";
import { Suspense } from "react";

import { ModelView } from "./view";

export const metadata: Metadata = { title: "Model card" };

export default function ModelPage() {
  return (
    <Suspense>
      <ModelView />
    </Suspense>
  );
}
