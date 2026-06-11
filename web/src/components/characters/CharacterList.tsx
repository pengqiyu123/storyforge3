import { useState } from "react";
import type { Character, Relationship } from "@/api/characters";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CreateCharacterDialog } from "./CreateCharacterDialog";

const roleLabels: Record<string, string> = {
  protagonist: "主角",
  major: "主要",
  minor: "次要",
  PROTAGONIST: "主角",
  MAJOR: "主要",
  MINOR: "次要"
};

export function CharacterList({
  characters,
  relationships,
  isLoading,
  onCreate,
  isPending
}: {
  characters?: Character[];
  relationships?: Relationship[];
  isLoading?: boolean;
  onCreate: (spec: string) => Promise<unknown>;
  isPending?: boolean;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (isLoading) {
    return <p className="text-sm text-zinc-500">正在读取角色...</p>;
  }

  return (
    <div className="space-y-5">
      <div className="flex justify-end">
        <CreateCharacterDialog isPending={isPending} onCreate={onCreate} />
      </div>
      {!characters?.length ? (
        <div className="rounded-lg border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500">还没有角色档案。</div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {characters.map((character) => (
            <Card key={character.name} className="cursor-pointer" onClick={() => setExpanded(expanded === character.name ? null : character.name)}>
              <CardHeader>
                <div className="flex items-center justify-between gap-4">
                  <CardTitle>{character.name}</CardTitle>
                  <Badge variant={character.role.toLowerCase() === "protagonist" ? "default" : "muted"}>{roleLabels[character.role] ?? character.role}</Badge>
                </div>
                <p className="text-sm text-zinc-400">{character.profile}</p>
              </CardHeader>
              {expanded === character.name ? (
                <CardContent className="space-y-3 text-sm leading-6 text-zinc-400">
                  <p>性格：{character.personality || "未记录"}</p>
                  <p>能力：{character.abilities.length ? character.abilities.join("、") : "未记录"}</p>
                  <p>弧线：{character.arc_direction || "未记录"}</p>
                </CardContent>
              ) : null}
            </Card>
          ))}
        </div>
      )}
      {relationships?.length ? (
        <Card>
          <CardHeader>
            <CardTitle>关系网络</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-zinc-400">
            {relationships.map((item) => (
              <p key={`${item.character_a}-${item.character_b}-${item.relation_type}`}>
                {item.character_a} - {item.character_b}：{item.description}
              </p>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
