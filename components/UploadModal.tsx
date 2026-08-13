import { Upload, X, File, AlertCircle } from "lucide-react";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";
import { useState, useRef } from "react";
import { toast } from "sonner";
import { useI18n } from "../lib/i18n";

interface UploadedFileItem {
  file: File;
  id: string;
  size: string;
}

interface UploadModalProps {
  open: boolean;
  onClose: () => void;
  onUpload: (files: File[]) => Promise<void> | void;
}

export function UploadModal({ open, onClose, onUpload }: UploadModalProps) {
  const { language, t } = useI18n();
  const [files, setFiles] = useState<UploadedFileItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + " " + sizes[i];
  };

  const validateFile = (file: File): string | null => {
    if (!file.name.endsWith(".csv")) {
      return language === "zh" ? "目前仅支持 CSV 文件" : "Only CSV files are accepted";
    }
    if (file.size > 50 * 1024 * 1024) {
      return language === "zh" ? "文件大小不能超过 50MB" : "File size must be less than 50MB";
    }
    return null;
  };

  const handleFiles = (newFiles: FileList | null) => {
    if (!newFiles) return;

    const validFiles: UploadedFileItem[] = [];
    
    Array.from(newFiles).forEach((file) => {
      const error = validateFile(file);
      if (error) {
        toast.error(error, {
          description: file.name,
        });
        return;
      }

      validFiles.push({
        file,
        id: `${Date.now()}-${file.name}`,
        size: formatFileSize(file.size),
      });
    });

    setFiles((prev) => [...prev, ...validFiles]);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleRemoveFile = (id: string) => {
    setFiles(files.filter((f) => f.id !== id));
  };

  const handleUpload = async () => {
    if (files.length === 0) return;

    setIsUploading(true);
    
    try {
      await onUpload(files.map((f) => f.file));
      setFiles([]);
    } catch {
      // The parent owns the user-facing error message. Keep the files so retry is possible.
    } finally {
      setIsUploading(false);
    }
  };

  const handleCancel = () => {
    setFiles([]);
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{language === "zh" ? "上传 CSV 数据" : "Upload CSV data"}</DialogTitle>
          <DialogDescription>
            {language === "zh" ? "可上传一个或多个 CSV 文件，每个文件不超过 50MB。" : "Upload one or more CSV files. Each file must be under 50MB."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Drag and Drop Area */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
              isDragging
                ? "border-blue-600 bg-blue-50 dark:bg-blue-900/10"
                : "border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800"
            }`}
          >
            <div className="flex flex-col items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-blue-100 dark:bg-blue-900 flex items-center justify-center">
                <Upload className="h-6 w-6 text-blue-600 dark:text-blue-400" />
              </div>
              
              <div>
                <p className="text-gray-900 dark:text-white mb-1">
                  {language === "zh" ? "将 CSV 文件拖到这里" : "Drag and drop CSV files here"}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">{language === "zh" ? "或" : "or"}</p>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                multiple
                onChange={handleFileInputChange}
                className="hidden"
              />

              <Button
                type="button"
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
              >
                {language === "zh" ? "从电脑选择文件" : "Choose files from computer"}
              </Button>

              <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mt-2">
                <AlertCircle className="h-3.5 w-3.5" />
                <span>{language === "zh" ? "支持 .csv · 最大 50MB · 可多选" : "Accepted: .csv · Up to 50MB · Multiple files allowed"}</span>
              </div>
            </div>
          </div>

          {/* File List */}
          {files.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {language === "zh" ? `待上传文件（${files.length}）` : `Files to upload (${files.length})`}
              </p>
              <div className="space-y-2 max-h-[200px] overflow-y-auto">
                {files.map((fileItem) => (
                  <div
                    key={fileItem.id}
                    className="flex items-center gap-3 p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg group hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors"
                  >
                    <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900 rounded flex items-center justify-center flex-shrink-0">
                      <File className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-900 dark:text-white truncate">
                        {fileItem.file.name}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {fileItem.size}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
                      onClick={() => handleRemoveFile(fileItem.id)}
                      aria-label={`Remove ${fileItem.file.name}`}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={handleCancel} disabled={isUploading}>
            {language === "zh" ? "取消" : "Cancel"}
          </Button>
          <Button
            onClick={handleUpload}
            disabled={files.length === 0 || isUploading}
            className="bg-blue-600 hover:bg-blue-700"
          >
            {isUploading ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
                {language === "zh" ? "正在上传…" : "Uploading…"}
              </>
            ) : (
              `${t("upload")} ${files.length > 0 ? `(${files.length})` : ""}`
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
