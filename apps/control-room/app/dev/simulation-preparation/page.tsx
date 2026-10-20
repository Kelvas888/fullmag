import { notFound } from "next/navigation";

import PreparationWindowPreview from "../../../scripts/fixtures/preparation-window-page";

export default function PreparationWindowPreviewPage() {
  if (process.env.NODE_ENV !== "development") notFound();
  return <PreparationWindowPreview />;
}
