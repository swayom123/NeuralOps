import { Suspense } from "react";
import { Console } from "@/components/console";
export default function Page() {
  return (
    <Suspense
      fallback={<main className="loading-page">Loading NeuralOps…</main>}
    >
      <Console />
    </Suspense>
  );
}
