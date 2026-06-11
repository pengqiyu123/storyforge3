import { getVersion } from "@tauri-apps/api/app";
import type { DownloadEvent, Update } from "@tauri-apps/plugin-updater";

export type UpdaterPhase =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "installing"
  | "restarting"
  | "upToDate"
  | "error";

export interface UpdateInfo {
  currentVersion: string;
  availableVersion: string;
  notes?: string;
  pubDate?: string;
}

export interface UpdateProgress {
  downloaded: number;
  total: number;
}

export type UpdateCheckResult =
  | { status: "up-to-date" }
  | {
      status: "available";
      info: UpdateInfo;
      downloadAndInstall: (onProgress?: (progress: UpdateProgress) => void) => Promise<void>;
    };

export async function getCurrentVersion(): Promise<string> {
  try {
    return await getVersion();
  } catch {
    return "";
  }
}

export async function checkForUpdate(): Promise<UpdateCheckResult> {
  const [{ check }, currentVersion] = await Promise.all([import("@tauri-apps/plugin-updater"), getCurrentVersion()]);
  const update = await check();

  if (!update) {
    return { status: "up-to-date" };
  }

  return {
    status: "available",
    info: {
      currentVersion,
      availableVersion: update.version,
      notes: updateNotes(update),
      pubDate: update.date
    },
    downloadAndInstall: (onProgress) => downloadAndInstall(update, onProgress)
  };
}

function updateNotes(update: Update): string | undefined {
  return (update as Update & { notes?: string }).notes ?? update.body;
}

export async function relaunchApp(): Promise<void> {
  const { relaunch } = await import("@tauri-apps/plugin-process");
  await relaunch();
}

async function downloadAndInstall(update: Update, onProgress?: (progress: UpdateProgress) => void): Promise<void> {
  let downloaded = 0;
  let total = 0;

  await update.downloadAndInstall((event: DownloadEvent) => {
    if (!onProgress) {
      return;
    }

    if (event.event === "Started") {
      downloaded = 0;
      total = event.data.contentLength ?? 0;
      onProgress({ downloaded, total });
      return;
    }

    if (event.event === "Progress") {
      downloaded += event.data.chunkLength;
      onProgress({ downloaded, total });
    }
  });
}
