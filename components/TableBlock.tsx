import { formatProseDecimals } from "../lib/numberFormat";

interface TableBlockProps {
  htmlString: string;
}

export function TableBlock({ htmlString }: TableBlockProps) {
  return (
    <div className="overflow-x-auto max-w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-sm p-3 my-2">
      <div
        dangerouslySetInnerHTML={{ __html: formatProseDecimals(htmlString) }}
        className="table-container"
        style={{ maxWidth: "100%" }}
      />
    </div>
  );
}
