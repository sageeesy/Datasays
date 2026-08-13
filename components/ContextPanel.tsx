import { File, Plus } from "lucide-react";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import { FileChip } from "./FileChip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { useState, useEffect } from "react";
import { useI18n } from "../lib/i18n";

interface FileInfo {
  id: string;
  name: string;
  size: string;
  rows: number;
  columns: number;
  preview: string[][];
}

interface ContextPanelProps {
  activeFiles: FileInfo[];
  recentFiles: FileInfo[];
  onAddFile: (fileId: string) => void;
  onRemoveFile: (fileId: string) => void;
  onUploadNew: () => void;
}

// Preview Table Component - Independent scrollable area
function PreviewTable({ previewFile }: { previewFile: FileInfo }) {
  const { t } = useI18n();
  return (
    <Card className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
      {/* Table container with horizontal scroll - independent from ScrollArea */}
      <div className="overflow-x-auto w-full">
        <table className="text-xs min-w-max">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
              {previewFile.preview[0].map((header, i) => (
                <th
                  key={i}
                  className="sticky top-0 bg-gray-50 dark:bg-gray-800/50 text-left px-4 py-2.5 text-gray-600 dark:text-gray-400 whitespace-nowrap font-medium z-10"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {previewFile.preview.slice(1, 4).map((row, i) => (
              <tr
                key={i}
                className={`border-b border-gray-100 dark:border-gray-800 last:border-0 ${
                  i % 2 === 0
                    ? "bg-white dark:bg-gray-800"
                    : "bg-gray-50/50 dark:bg-gray-800/30"
                }`}
              >
                {row.map((cell, j) => (
                  <td
                    key={j}
                    className="px-4 py-2 text-gray-800 dark:text-gray-300 whitespace-nowrap"
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* Footer info */}
      <div className="px-4 py-2.5 border-t border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/30">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {t("showingRows", { shown: Math.min(3, previewFile.rows), total: previewFile.rows, columns: previewFile.columns })}
        </p>
      </div>
    </Card>
  );
}

export function ContextPanel({
  activeFiles,
  recentFiles,
  onAddFile,
  onRemoveFile,
  onUploadNew,
}: ContextPanelProps) {
  const { t } = useI18n();
  const [previewFileId, setPreviewFileId] = useState<string>("");

  useEffect(() => {
    if (activeFiles.length > 0 && !previewFileId) {
      setPreviewFileId(activeFiles[0].id);
    }
  }, [activeFiles, previewFileId]);

  const previewFile =
    activeFiles.find((f) => f.id === previewFileId) || activeFiles[0];

  // Filter recent files to exclude active ones
  const availableRecentFiles = recentFiles.filter(
    (rf) => !activeFiles.find((af) => af.id === rf.id),
  );

  return (
    <aside className="flex h-full w-[min(23rem,92vw)] shrink-0 flex-col border-l border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900 lg:w-[360px]" aria-label={t("currentContext")}>
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-800 flex-shrink-0">
        <h3 className="text-gray-900 dark:text-white mb-1 font-semibold">
          {t("currentContext")}
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {t("contextDescription")}
        </p>
      </div>

      {/* Scrollable area for Active Files and Recent Uploads only */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-4 space-y-6">
          {/* Active Files Section */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {t("activeFiles")}
              </h4>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 text-xs gap-1"
                onClick={onUploadNew}
              >
                <Plus className="h-3 w-3" />
                {t("upload")}
              </Button>
            </div>

            {activeFiles.length === 0 ? (
              <Card className="p-4 bg-white dark:bg-gray-800 text-center border border-gray-200 dark:border-gray-700">
                <File className="h-8 w-8 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {t("noFiles")}
                </p>
              </Card>
            ) : (
              <div className="flex flex-wrap gap-2">
                {activeFiles.map((file) => (
                  <FileChip
                    key={file.id}
                    fileName={file.name}
                    selected={true}
                    removable={true}
                    onRemove={() => onRemoveFile(file.id)}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Recent Uploads Section */}
          {availableRecentFiles.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {t("recentUploads")}
              </h4>
              <div className="space-y-1.5">
                {availableRecentFiles.slice(0, 5).map((file) => (
                  <Card
                    key={file.id}
                    className="p-2 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors cursor-pointer border border-gray-200 dark:border-gray-700"
                    onClick={() => onAddFile(file.id)}
                  >
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 bg-gray-100 dark:bg-gray-700 rounded flex items-center justify-center flex-shrink-0">
                        <File className="h-3.5 w-3.5 text-gray-500 dark:text-gray-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-gray-900 dark:text-white truncate">
                          {file.name}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {file.size}
                        </p>
                      </div>
                      <Plus className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" />
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Preview Section - Independent from ScrollArea */}
      {previewFile && (
        <div className="flex-shrink-0 border-t border-gray-200 dark:border-gray-800 flex flex-col min-h-0">
          <div className="p-4 pb-2 flex items-center justify-between">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {t("preview")}
            </h4>
            {activeFiles.length > 1 && (
              <Select value={previewFileId} onValueChange={setPreviewFileId}>
                <SelectTrigger className="w-36 h-7 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {activeFiles.map((file) => (
                    <SelectItem
                      key={file.id}
                      value={file.id}
                      className="text-xs"
                    >
                      {file.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          <div className="px-4 pb-4 overflow-x-auto w-full">
            <PreviewTable previewFile={previewFile} />
          </div>
        </div>
      )}
    </aside>
  );
}
