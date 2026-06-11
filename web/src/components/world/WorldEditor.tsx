import { useEffect, useState } from "react";
import { toast } from "sonner";
import type { WorldConfig } from "@/api/world";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface WorldEditorProps {
  bookId: string;
  genre: string;
  world?: WorldConfig | null;
  isLoading?: boolean;
  onBuild: (data: { genre: string; seedBrief: string }) => Promise<unknown>;
  onUpdate: (world: Omit<WorldConfig, "book_id">) => Promise<unknown>;
  isPending?: boolean;
}

export function WorldEditor({ genre, world, isLoading = false, onBuild, onUpdate, isPending = false }: WorldEditorProps) {
  const [seedBrief, setSeedBrief] = useState("");
  const [draft, setDraft] = useState<Omit<WorldConfig, "book_id">>({
    setting: "",
    power_system: "",
    core_conflict: "",
    rules: []
  });

  useEffect(() => {
    if (world) {
      setDraft({
        setting: world.setting,
        power_system: world.power_system,
        core_conflict: world.core_conflict,
        rules: world.rules
      });
    }
  }, [world]);

  async function buildWorld() {
    await onBuild({ genre, seedBrief: seedBrief || "现代都市里的异常觉醒故事" });
    toast.success("世界观已构建");
  }

  async function saveWorld() {
    await onUpdate(draft);
    toast.success("世界观已保存");
  }

  if (isLoading) {
    return <p className="text-sm text-zinc-500">正在读取世界观...</p>;
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
      <Card>
        <CardHeader>
          <CardTitle>世界观构建</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm leading-6 text-zinc-400">首次进入可以用一句种子设定构建世界观，之后再手动细调。</p>
          <div className="grid gap-2">
            <Label htmlFor="seed_brief">种子设定</Label>
            <Input id="seed_brief" value={seedBrief} onChange={(event) => setSeedBrief(event.target.value)} placeholder="例如：低存在感少年被检测中心追踪" />
          </div>
          <Button onClick={buildWorld} disabled={isPending}>
            构建世界观
          </Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{world ? "世界观编辑" : "尚未构建"}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          <WorldTextarea label="设定" value={draft.setting} onChange={(value) => setDraft({ ...draft, setting: value })} />
          <WorldTextarea label="力量体系" value={draft.power_system} onChange={(value) => setDraft({ ...draft, power_system: value })} />
          <WorldTextarea label="核心冲突" value={draft.core_conflict} onChange={(value) => setDraft({ ...draft, core_conflict: value })} />
          <WorldTextarea label="世界规则" value={draft.rules.join("\n")} onChange={(value) => setDraft({ ...draft, rules: value.split("\n").filter(Boolean) })} />
          <Button onClick={saveWorld} disabled={isPending || !world}>
            保存修改
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function WorldTextarea({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="grid gap-2 md:grid-cols-[7rem_1fr] md:items-start">
      <span className="text-sm font-medium text-zinc-300">{label}</span>
      <textarea
        className="min-h-24 rounded-md border border-zinc-800 bg-zinc-950 p-3 text-sm leading-6 text-zinc-100 outline-none focus:border-amber-300/70"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
