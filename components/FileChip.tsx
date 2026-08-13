import { File, X } from "lucide-react";

interface FileChipProps {
  fileName: string;
  selected?: boolean;
  removable?: boolean;
  onRemove?: () => void;
  onClick?: () => void;
}

export function FileChip({
  fileName,
  selected = false,
  removable = false,
  onRemove,
  onClick,
}: FileChipProps) {
  const handleClick = () => {
    if (onClick) {
      onClick();
    }
  };

  const handleRemove = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onRemove) {
      onRemove();
    }
  };

  return (
    <div className={`inline-flex max-w-full items-center overflow-hidden rounded-md border text-xs font-medium transition-colors ${
      selected
        ? "border-blue-600 bg-blue-600 text-white"
        : "border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
    }`}>
      <button
        type="button"
        className={`flex min-w-0 items-center gap-1.5 px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-300 ${
          onClick ? "cursor-pointer hover:bg-black/10" : "cursor-default"
        }`}
        onClick={handleClick}
        disabled={!onClick}
        aria-pressed={onClick ? selected : undefined}
        title={fileName}
      >
        <File className="h-3 w-3 shrink-0" />
        <span className="max-w-40 truncate">{fileName}</span>
      </button>
      {removable && (
        <button
          type="button"
          onClick={handleRemove}
          className="flex self-stretch items-center border-l border-white/20 px-1.5 hover:bg-black/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-300"
          aria-label={`Remove ${fileName}`}
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}
