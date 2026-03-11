import { BarChart3, Clock } from "lucide-react";

export default function AnalyticsPage() {
  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <div className="p-2 bg-primary-100 dark:bg-primary-900/20 rounded-lg">
          <BarChart3 className="w-6 h-6 text-primary-500" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            Analytics
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            Usage, costs, and performance insights
          </p>
        </div>
      </div>

      <div className="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-10 text-center">
        <div className="flex justify-center mb-4">
          <div className="p-3 bg-neutral-100 dark:bg-neutral-700 rounded-full">
            <Clock className="w-8 h-8 text-neutral-400" />
          </div>
        </div>
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2">
          Coming Soon
        </h2>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 max-w-md mx-auto">
          Analytics for desktop users is planned for a future release. Usage tracking,
          cost breakdowns, and model performance insights will be available here.
        </p>
      </div>
    </div>
  );
}
