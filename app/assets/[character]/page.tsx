import type { Metadata } from "next";
import ReviewClient from "./review-client";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ character: string }> }): Promise<Metadata> {
  const { character } = await params;
  return { title: `${character} — asset review` };
}

export default async function CharacterReview({ params }: { params: Promise<{ character: string }> }) {
  const { character } = await params;
  return <ReviewClient character={character} />;
}
