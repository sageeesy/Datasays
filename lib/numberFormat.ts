export function formatFixedNumber(value: number): string {
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatDisplayValue(value: unknown, fixed = true): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return fixed ? formatFixedNumber(value) : String(value);
  }

  if (fixed && typeof value === "string") {
    const match = value.trim().match(/^([$¥￥]?)(-?\d[\d,]*(?:\.\d+)?(?:[eE][+-]?\d+)?)(%?)$/);
    if (match) {
      const numericValue = Number(match[2].replace(/,/g, ""));
      if (Number.isFinite(numericValue)) {
        return `${match[1]}${formatFixedNumber(numericValue)}${match[3]}`;
      }
    }
  }

  return String(value ?? "-");
}

export function formatProseDecimals(content: string): string {
  return content
    .split(/(```[\s\S]*?```|`[^`]*`)/g)
    .map((part, index) => {
      if (index % 2 === 1) return part;
      return part.replace(/(?<![\w-])-?\d+\.\d{3,}(?:[eE][+-]?\d+)?/g, (match) => {
        const value = Number(match);
        return Number.isFinite(value) ? value.toFixed(2) : match;
      });
    })
    .join("");
}
