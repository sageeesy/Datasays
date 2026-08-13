import { BarChart3, FlaskConical, Languages, Menu, Moon, PanelRightClose, PanelRightOpen, ShieldCheck, Sun, Upload } from "lucide-react";
import { Button } from "./ui/button";
import { useI18n } from "../lib/i18n";
import type { AppPage } from "../lib/appTypes";

interface ConversationalHeaderProps {
  currentPage: AppPage;
  onNavigate: (page: AppPage) => void;
  isDark: boolean;
  toggleTheme: () => void;
  onUpload: () => void;
  showPanel: boolean;
  togglePanel: () => void;
  showSidebar: boolean;
  toggleSidebar: () => void;
}

const pageIcons = {
  analysis: ShieldCheck,
  comparison: FlaskConical,
  dashboard: BarChart3,
};

export function ConversationalHeader({
  currentPage,
  onNavigate,
  isDark,
  toggleTheme,
  onUpload,
  showPanel,
  togglePanel,
  showSidebar,
  toggleSidebar,
}: ConversationalHeaderProps) {
  const { language, setLanguage, t } = useI18n();

  return (
    <header className="z-[60] shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      <div className="flex h-16 items-center gap-2 px-3 sm:px-5">
        {currentPage === "analysis" && (
          <Button variant="ghost" size="icon" onClick={toggleSidebar} className={showSidebar ? "lg:hidden" : ""} aria-label={t("conversations")}>
            <Menu className="h-5 w-5" />
          </Button>
        )}

        <button type="button" onClick={() => onNavigate("analysis")} className="flex shrink-0 items-center gap-2 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
          <span className="flex h-9 w-9 items-center justify-center rounded-md bg-blue-600 text-sm font-semibold text-white">D</span>
          <span className="hidden text-left sm:block">
            <span className="block text-sm font-semibold text-gray-950 dark:text-white">DataSays</span>
            <span className="block text-[11px] text-gray-500 dark:text-gray-400">Evidence-first analytics</span>
          </span>
        </button>

        <nav className="ml-1 flex min-w-0 flex-1 items-center justify-center gap-1 overflow-x-auto sm:ml-4" aria-label="Primary navigation">
          {(["analysis", "comparison", "dashboard"] as AppPage[]).map((page) => {
            const Icon = pageIcons[page];
            const active = currentPage === page;
            return (
              <button
                key={page}
                type="button"
                onClick={() => onNavigate(page)}
                className={`flex h-9 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors sm:px-3 sm:text-sm ${active ? "bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300" : "text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"}`}
                aria-current={active ? "page" : undefined}
              >
                <Icon className="h-4 w-4" />
                <span className="hidden md:inline">{t(page)}</span>
              </button>
            );
          })}
        </nav>

        <div className="flex shrink-0 items-center gap-1">
          {currentPage === "analysis" && (
            <>
              <Button variant="ghost" size="icon" onClick={onUpload} aria-label={t("upload")} title={t("upload")}>
                <Upload className="h-5 w-5" />
              </Button>
              <Button variant="ghost" size="icon" onClick={togglePanel} aria-label={t("currentContext")} title={t("currentContext")}>
                {showPanel ? <PanelRightClose className="h-5 w-5" /> : <PanelRightOpen className="h-5 w-5" />}
              </Button>
            </>
          )}

          <Button
            variant="ghost"
            size="sm"
            onClick={() => setLanguage(language === "zh" ? "en" : "zh")}
            className="h-9 gap-1 px-2 text-xs"
            aria-label={t("language")}
            title={language === "zh" ? t("english") : t("chinese")}
          >
            <Languages className="h-4 w-4" />
            <span className="hidden sm:inline">{language === "zh" ? "EN" : "中文"}</span>
          </Button>
          <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={isDark ? "Light theme" : "Dark theme"}>
            {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </Button>
        </div>
      </div>
    </header>
  );
}
