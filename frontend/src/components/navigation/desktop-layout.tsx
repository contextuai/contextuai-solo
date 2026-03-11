import { Outlet } from "react-router-dom";
import DesktopSidebar from "./desktop-sidebar";

export function DesktopLayout() {
  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-[#242523]">
      <div className="flex">
        <DesktopSidebar />
        <main className="flex-1 transition-all duration-300">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
