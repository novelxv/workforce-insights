import type { Metadata } from "next";
import { Suspense } from "react";

import { DefinitionsView } from "./view";

export const metadata: Metadata = { title: "Definitions and exports" };

export default function DefinitionsPage() {
  return (
    <Suspense>
      <DefinitionsView />
    </Suspense>
  );
}
