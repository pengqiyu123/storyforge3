import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import type { CreateShortRequest } from "@/api/shorts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

interface CreateShortDialogProps {
  isPending?: boolean;
  onCreate: (data: CreateShortRequest) => Promise<{ book_id: string }>;
}

const initialForm: CreateShortRequest = {
  title: "",
  genre: "urban",
  target_chars: 10_000,
  premise: "",
  style: ""
};

export function CreateShortDialog({ isPending = false, onCreate }: CreateShortDialogProps) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<CreateShortRequest>(initialForm);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const story = await onCreate(form);
    toast.success("短篇已创建");
    setOpen(false);
    setForm(initialForm);
    navigate(`/shorts/${story.book_id}`);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4" />
          创建短篇
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>创建短篇</DialogTitle>
          <DialogDescription>建立一个独立短篇项目。</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="grid gap-5 p-6">
            <div className="grid gap-2">
              <Label htmlFor="short-title">标题</Label>
              <Input id="short-title" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="short-genre">类型</Label>
              <Select id="short-genre" value={form.genre} onChange={(event) => setForm({ ...form, genre: event.target.value })}>
                <option value="xuanhuan">玄幻</option>
                <option value="xianxia">仙侠</option>
                <option value="urban">都市</option>
                <option value="horror">悬疑惊悚</option>
                <option value="sci-fi">科幻</option>
                <option value="other">其他</option>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="short-target">目标字数</Label>
              <Input
                id="short-target"
                type="number"
                min={5000}
                max={20000}
                value={form.target_chars}
                onChange={(event) => setForm({ ...form, target_chars: Number(event.target.value) })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="short-premise">核心设定</Label>
              <textarea
                id="short-premise"
                className="min-h-24 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none transition-colors placeholder:text-zinc-600 focus:border-amber-300/70 focus:ring-2 focus:ring-amber-300/10"
                value={form.premise}
                onChange={(event) => setForm({ ...form, premise: event.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="short-style">风格</Label>
              <Input id="short-style" value={form.style} onChange={(event) => setForm({ ...form, style: event.target.value })} />
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
