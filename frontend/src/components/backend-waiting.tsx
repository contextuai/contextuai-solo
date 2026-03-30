import { Loader2, WifiOff } from "lucide-react";
import { useBackendStatus } from "@/contexts/backend-status-context";

export function BackendWaiting() {
  const { status, retry } = useBackendStatus();

  if (status === "ready") return null;

  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      {status === "checking" ? (
        <>
          <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            Waiting for backend to start...
          </p>
        </>
      ) : (
        <>
          <WifiOff className="w-8 h-8 text-neutral-400" />
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            Backend is not responding. Make sure the server is running.
          </p>
          <button
            onClick={retry}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors"
          >
            Retry
          </button>
        </>
      )}
    </div>
  );
}
