import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { checkForUpdate, relaunchApp, type UpdateCheckResult, type UpdateInfo, type UpdateProgress } from "@/lib/updater";

const DISMISSED_VERSION_KEY = "storyforge3:update:dismissedVersion";

interface UpdateContextValue {
  hasUpdate: boolean;
  updateInfo: UpdateInfo | null;
  isChecking: boolean;
  isUpdating: boolean;
  downloadProgress: UpdateProgress | null;
  error: string | null;
  isDismissed: boolean;
  checkUpdate: () => Promise<boolean>;
  dismissUpdate: () => void;
  startUpdate: () => Promise<void>;
}

interface UpdateProviderProps {
  children: React.ReactNode;
  autoCheck?: boolean;
}

const UpdateContext = createContext<UpdateContextValue | null>(null);

export function UpdateProvider({ children, autoCheck = true }: UpdateProviderProps) {
  const [updateResult, setUpdateResult] = useState<Extract<UpdateCheckResult, { status: "available" }> | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState<UpdateProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDismissed, setIsDismissed] = useState(false);
  const checkingRef = useRef(false);

  const checkUpdate = useCallback(async () => {
    if (checkingRef.current) {
      return false;
    }

    checkingRef.current = true;
    setIsChecking(true);
    setError(null);

    try {
      const result = await checkForUpdate();
      if (result.status === "available") {
        setUpdateResult(result);
        setIsDismissed(localStorage.getItem(DISMISSED_VERSION_KEY) === result.info.availableVersion);
        return true;
      }

      setUpdateResult(null);
      setIsDismissed(false);
      return false;
    } catch (err) {
      const message = err instanceof Error ? err.message : "检查更新失败";
      setError(message);
      setUpdateResult(null);
      setIsDismissed(false);
      return false;
    } finally {
      checkingRef.current = false;
      setIsChecking(false);
    }
  }, []);

  const dismissUpdate = useCallback(() => {
    if (!updateResult) {
      return;
    }

    localStorage.setItem(DISMISSED_VERSION_KEY, updateResult.info.availableVersion);
    setIsDismissed(true);
  }, [updateResult]);

  const startUpdate = useCallback(async () => {
    if (!updateResult) {
      return;
    }

    setIsUpdating(true);
    setError(null);
    setDownloadProgress(null);

    try {
      await updateResult.downloadAndInstall((progress) => setDownloadProgress(progress));
      await relaunchApp();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新失败");
      setIsUpdating(false);
    }
  }, [updateResult]);

  useEffect(() => {
    if (!autoCheck) {
      return;
    }

    const timer = window.setTimeout(() => {
      void checkUpdate();
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [autoCheck, checkUpdate]);

  const value = useMemo<UpdateContextValue>(
    () => ({
      hasUpdate: Boolean(updateResult),
      updateInfo: updateResult?.info ?? null,
      isChecking,
      isUpdating,
      downloadProgress,
      error,
      isDismissed,
      checkUpdate,
      dismissUpdate,
      startUpdate
    }),
    [checkUpdate, dismissUpdate, downloadProgress, error, isChecking, isDismissed, isUpdating, startUpdate, updateResult]
  );

  return <UpdateContext.Provider value={value}>{children}</UpdateContext.Provider>;
}

export function useUpdate() {
  const context = useContext(UpdateContext);
  if (!context) {
    throw new Error("useUpdate must be used within UpdateProvider");
  }
  return context;
}
