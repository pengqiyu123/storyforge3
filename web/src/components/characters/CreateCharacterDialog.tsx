import { useState } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export function CreateCharacterDialog({ isPending, onCreate }: { isPending?: boolean; onCreate: (spec: string) => Promise<unknown> }) {
  const [open, setOpen] = useState(false);
  const [spec, setSpec] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onCreate(spec);
    toast.success("角色已创建");
    setSpec("");
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4" />
          添加角色
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>添加角色</DialogTitle>
          <DialogDescription>用自然语言描述角色定位、性格和能力。</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit}>
          <div className="p-6">
            <textarea
              className="min-h-40 w-full rounded-md border border-zinc-800 bg-zinc-950 p-3 text-sm leading-6 text-zinc-100 outline-none focus:border-amber-300/70"
              value={spec}
              onChange={(event) => setSpec(event.target.value)}
              required
            />
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
