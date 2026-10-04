import Link from "next/link";
import { PlatformDot } from "@/components/editorial";
import { dateShort, pct } from "@/lib/format";
import type { Neighbor, PostCard } from "@/lib/types";
import { cn } from "@/lib/utils";

export function IndexPill({ value }: { value: number }) {
  const tone = value >= 1.25 ? "bg-lime text-lime-ink border-ink" : value < 0.8 ? "border-alert text-alert" : "border-line text-ink-2";
  return <span className={cn("num inline-block min-w-12 border px-1.5 py-0.5 text-center text-xs", tone)} title="Engagement rate relative to the platform median">{value.toFixed(2)}×</span>;
}

export function PostCardList({ posts, empty }: { posts: PostCard[]; empty?: string }) {
  if (posts.length === 0) return <p className="text-sm text-mute">{empty ?? "No posts."}</p>;
  return (
    <ul className="divide-y divide-line border-y border-line">
      {posts.map((p) => (
        <li key={p.post_id}>
          <Link href={`/memory/${p.post_id}`} className="grid grid-cols-[auto_1fr_auto] items-start gap-3 py-3 hover:bg-paper-2/60">
            <PlatformDot platform={p.platform} />
            <div className="min-w-0">
              <p className="truncate text-sm">{p.caption_preview}</p>
              <p className="mt-0.5 truncate text-xs text-mute">{p.format} · {p.hook} · {p.topic} · {dateShort(p.published_at)}</p>
            </div>
            <div className="text-right">
              <p className="num text-sm">{pct(p.engagement_rate, 2)}</p>
              <IndexPill value={p.performance_index} />
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function NeighborList({ neighbors }: { neighbors: Neighbor[] }) {
  return (
    <ul className="divide-y divide-line border-y border-line">
      {neighbors.map((n) => (
        <li key={n.post_id}>
          <Link href={`/memory/${n.post_id}`} className="grid grid-cols-[auto_1fr_auto] items-start gap-3 py-3 hover:bg-paper-2/60">
            <PlatformDot platform={n.platform} />
            <div className="min-w-0">
              <p className="truncate text-sm">{n.caption_preview}</p>
              <p className="mt-0.5 truncate text-xs text-mute">
                {n.format} · {n.hook} · {dateShort(n.published_at)} · shares {n.shared_attributes.length ? n.shared_attributes.join(", ") : "no attributes"}
              </p>
            </div>
            <div className="text-right">
              <p className="num text-sm">{pct(n.engagement_rate, 2)}</p>
              <p className="num text-[11px] text-mute" title="Blend of caption text similarity and shared attributes">sim {n.similarity.toFixed(2)}</p>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
