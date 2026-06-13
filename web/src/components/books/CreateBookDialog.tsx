import { useState } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { type CreateBookRequest } from "@/api/books";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

interface CreateBookDialogProps {
  isPending?: boolean;
  onCreate: (data: CreateBookRequest) => Promise<unknown>;
}

export function CreateBookDialog({ isPending = false, onCreate }: CreateBookDialogProps) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<CreateBookRequest>({
    title: "",
    genre: "urban",
    platform: "tomato",
    target_chapters: 100,
    chapter_word_count: 2500
  });

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onCreate(form);
    toast.success("新书已创建");
    setOpen(false);
    setForm({ title: "", genre: "urban", platform: "tomato", target_chapters: 100, chapter_word_count: 2500 });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4" />
          创建新书
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>创建新书</DialogTitle>
          <DialogDescription>建立一本可连续生产的长篇小说项目。</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="grid gap-5 p-6">
            <div className="grid gap-2">
              <Label htmlFor="title">书名</Label>
              <Input id="title" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="genre">类型</Label>
              <Select id="genre" value={form.genre} onChange={(event) => setForm({ ...form, genre: event.target.value })}>
                <option value="urban">都市玄幻</option>
                <option value="xuanhuan">玄幻</option>
                <option value="xianxia">仙侠</option>
                <option value="horror">悬疑惊悚</option>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="platform">平台</Label>
              <Select id="platform" value={form.platform} onChange={(event) => setForm({ ...form, platform: event.target.value })}>
                <option value="tomato">番茄小说</option>
                <option value="qidian">起点中文网</option>
                <option value="feilu">飞卢</option>
              </Select>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="target_chapters">目标章节</Label>
                <Input
                  id="target_chapters"
                  min={1}
                  type="number"
                  value={form.target_chapters}
                  onChange={(event) => setForm({ ...form, target_chapters: Number(event.target.value) })}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="chapter_word_count">单章字数</Label>
                <Input
                  id="chapter_word_count"
                  min={500}
                  type="number"
                  value={form.chapter_word_count}
                  onChange={(event) => setForm({ ...form, chapter_word_count: Number(event.target.value) })}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button type="submit" disabled={isPending}>
              创建
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
