import { User, Bot, ChevronDown, ChevronRight, CheckCircle, AlertCircle, File } from "lucide-react";
import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { useState } from "react";
import { parseContentWithTables } from "../lib/tableParser";
import { TableBlock } from "./TableBlock";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { formatDisplayValue, formatFixedNumber, formatProseDecimals } from "../lib/numberFormat";

interface ConversationalMessageProps {
  type: "user" | "ai";
  content: string;
  code?: string;
  status?: "success" | "error" | "autofix";
  timestamp: string;
  output?: {
    type: "table" | "chart" | "number" | "text";
    data: any;
    analysis_result?: any;
  };
  filesUsed?: string[];
}

const COLORS = ["#2563EB", "#3B82F6", "#60A5FA", "#93C5FD", "#BFDBFE"];

export function ConversationalMessage({ 
  type, 
  content, 
  code, 
  status, 
  timestamp,
  output,
  filesUsed = []
}: ConversationalMessageProps) {
  const [isCodeOpen, setIsCodeOpen] = useState(false);

  if (type === "user") {
    return (
      <div className="flex gap-3 justify-end">
        <div className="max-w-2xl">
          <Card className="px-4 py-3 bg-gray-100 dark:bg-gray-800 border-gray-200 dark:border-gray-700">
            <div className="text-gray-900 dark:text-white">{content}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-2">{timestamp}</div>
          </Card>
          {filesUsed.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2 justify-end">
              {filesUsed.map((fileName, idx) => (
                <Badge
                  key={idx}
                  variant="secondary"
                  className="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700"
                >
                  <File className="h-3 w-3 mr-1" />
                  {fileName}
                </Badge>
              ))}
            </div>
          )}
        </div>
        <div className="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center flex-shrink-0">
          <User className="h-4 w-4 text-gray-600 dark:text-gray-300" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-600 to-blue-400 flex items-center justify-center flex-shrink-0 mt-1">
        <Bot className="h-4 w-4 text-white" />
      </div>
      <div className="flex-1 max-w-3xl">
        <Card className="px-4 py-3 bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm text-gray-600 dark:text-gray-400">DataSays</span>
            {status === "success" && (
              <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300 text-xs">
                <CheckCircle className="h-3 w-3 mr-1" />
                Executed successfully
              </Badge>
            )}
            {status === "autofix" && (
              <Badge className="bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300 text-xs">
                Auto-repair round #1
              </Badge>
            )}
            {status === "error" && (
              <Badge className="bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300 text-xs">
                <AlertCircle className="h-3 w-3 mr-1" />
                Error
              </Badge>
            )}
          </div>
          
          <div className="text-gray-900 dark:text-white mb-3">
            {parseContentWithTables(content).map((block, idx) => {
              if (block.type === "table") {
                return <TableBlock key={idx} htmlString={block.content} />;
              } else {
                return (
                  <div key={idx} className="mb-2">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {formatProseDecimals(block.content)}
                    </ReactMarkdown>
                  </div>
                );
              }
            })}
          </div>
          
          {/* Inline Output */}
          {output && (
            <div className="mt-4 mb-3">
              {output.type === "number" && (
                <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 text-center border border-gray-200 dark:border-gray-700">
                  <div className="text-3xl text-blue-600 mb-1 tabular-nums">{formatDisplayValue(output.data.value)}</div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">{output.data.label}</div>
                </div>
              )}

              {output.type === "table" && (
                <div className="bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          {output.data.headers.map((header: string, i: number) => (
                            <TableHead key={i}>{header}</TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {output.data.rows.map((row: any[], i: number) => (
                          <TableRow key={i}>
                            {row.map((cell: any, j: number) => (
                              <TableCell key={j} className={j === 0 ? "font-medium" : "tabular-nums"}>{formatDisplayValue(cell, j !== 0)}</TableCell>
                            ))}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              )}

              {output.type === "chart" && (
                <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                  <div className="text-sm text-gray-600 dark:text-gray-400 mb-3">{output.data.title}</div>
                  <ResponsiveContainer width="100%" height={280}>
                    {output.data.chartType === "bar" ? (
                      <BarChart data={output.data.data}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                        <YAxis tick={{ fontSize: 12 }} tickFormatter={(value) => formatFixedNumber(Number(value))} />
                        <Tooltip formatter={(value) => formatDisplayValue(value)} />
                        <Bar dataKey="value" fill="#2563EB" radius={[6, 6, 0, 0]} />
                      </BarChart>
                    ) : output.data.chartType === "line" ? (
                      <LineChart data={output.data.data}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                        <YAxis tick={{ fontSize: 12 }} tickFormatter={(value) => formatFixedNumber(Number(value))} />
                        <Tooltip formatter={(value) => formatDisplayValue(value)} />
                        <Line type="monotone" dataKey="value" stroke="#2563EB" strokeWidth={2} dot={{ fill: "#2563EB", r: 4 }} />
                      </LineChart>
                    ) : (
                      <PieChart>
                        <Pie
                          data={output.data.data}
                          cx="50%"
                          cy="50%"
                          labelLine={false}
                          label={(entry) => `${entry.name}: ${formatFixedNumber(Number(entry.value))}%`}
                          outerRadius={90}
                          fill="#2563EB"
                          dataKey="value"
                        >
                          {output.data.data.map((_: any, index: number) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(value) => formatDisplayValue(value)} />
                      </PieChart>
                    )}
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          )}
          
          {/* Collapsible Code */}
          {code && (
            <Collapsible open={isCodeOpen} onOpenChange={setIsCodeOpen} className="mt-3">
              <div className="bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                <CollapsibleTrigger className="w-full p-3 flex items-center justify-between hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                  <div className="flex items-center gap-2">
                    {isCodeOpen ? (
                      <ChevronDown className="h-4 w-4 text-gray-500" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-gray-500" />
                    )}
                    <span className="text-sm text-gray-600 dark:text-gray-300">
                      View generated Python code
                    </span>
                  </div>
                  <Badge variant="secondary" className="text-xs">Python</Badge>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="px-3 pb-3">
                    <pre className="bg-gray-900 dark:bg-gray-950 text-gray-100 p-4 rounded-lg text-sm overflow-x-auto">
                      <code>{code}</code>
                    </pre>
                  </div>
                </CollapsibleContent>
              </div>
            </Collapsible>
          )}
          
          <div className="text-xs text-gray-400 dark:text-gray-500 mt-3">{timestamp}</div>
        </Card>
      </div>
    </div>
  );
}
