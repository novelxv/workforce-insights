import type { Metadata } from "next";
import { Suspense } from "react";

import { AskView } from "./view";

export const metadata: Metadata = { title: "Ask" };

export default function AskPage() {
  return (
    <Suspense>
      <AskView />
    </Suspense>
  );
}
