import { useState } from "react";
import { toast } from "sonner";
import type { VolumeOutline } from "@/api/volumes";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function VolumeList({
  volumes,
  isLoading,
  onPlan,
  isPending
}: {
  volumes?: VolumeOutline[];
  isLoading?: boolean;
  onPlan: (data: { volumeCount: number; totalChapters: number }) => Promise<unknown>;
  isPending?: boolean;
}) {
  const [volumeCount, setVolumeCount] = useState(1);
  const [totalChapters, setTotalChapters] = useState(10);

  async function plan() {
    await onPlan({ volumeCount, totalChapters });
    toast.success("卷规划已生成");
  }

  if (isLoading) {
    return <p className="text-sm text-zinc-500">正在读取卷规划...</p>;
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[22rem_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>规划卷</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="volume_count">卷数</Label>
            <Input id="volume_count" type="number" min={1} value={volumeCount} onChange={(event) => setVolumeCount(Number(event.target.value))} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="total_chapters">总章节</Label>
            <Input id="total_chapters" type="number" min={1} value={totalChapters} onChange={(event) => setTotalChapters(Number(event.target.value))} />
          </div>
          <Button onClick={plan} disabled={isPending}>
            规划卷
          </Button>
        </CardContent>
      </Card>
      <div className="space-y-4">
        {!volumes?.length ? (
          <div className="rounded-lg border border-dashed border-zinc-800 p-8 text-sm text-zinc-500">还没有卷纲。</div>
        ) : (
          volumes.map((volume) => (
            <Card key={volume.volume_no}>
              <CardHeader>
                <CardTitle>
                  第 {volume.volume_no} 卷：{volume.title}
                </CardTitle>
                <p className="text-sm text-zinc-500">{volume.chapter_count} 章</p>
              </CardHeader>
              <CardContent className="space-y-3 text-sm leading-6 text-zinc-400">
                <p>{volume.synopsis}</p>
                {volume.key_scenes.length ? <p>关键场景：{volume.key_scenes.join(" / ")}</p> : null}
                {volume.rhythm_curve.length ? <p>节奏：{volume.rhythm_curve.join(" -> ")}</p> : null}
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
