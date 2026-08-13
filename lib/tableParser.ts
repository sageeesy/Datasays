/**
 * Utility functions for parsing and rendering content with HTML tables
 */

export interface ContentBlock {
  type: "text" | "table";
  content: string;
}

/**
 * Parse content string and split into text and table blocks
 * Detects HTML table tags and extracts them separately
 */
export function parseContentWithTables(content: string): ContentBlock[] {
  const blocks: ContentBlock[] = [];
  
  // Regex to match HTML table tags (case-insensitive, handles attributes)
  const tableRegex = /<table[\s\S]*?<\/table>/gi;
  
  let lastIndex = 0;
  let match;
  
  while ((match = tableRegex.exec(content)) !== null) {
    // Add text before the table
    if (match.index > lastIndex) {
      const textContent = content.substring(lastIndex, match.index).trim();
      if (textContent) {
        blocks.push({ type: "text", content: textContent });
      }
    }
    
    // Add the table
    blocks.push({ type: "table", content: match[0] });
    
    lastIndex = match.index + match[0].length;
  }
  
  // Add remaining text after the last table
  if (lastIndex < content.length) {
    const textContent = content.substring(lastIndex).trim();
    if (textContent) {
      blocks.push({ type: "text", content: textContent });
    }
  }
  
  // If no tables found, return the entire content as text
  if (blocks.length === 0) {
    blocks.push({ type: "text", content: content });
  }
  
  return blocks;
}

/**
 * Check if content contains HTML table tags
 */
export function hasTable(content: string): boolean {
  return /<table[\s\S]*?<\/table>/gi.test(content);
}


