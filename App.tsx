import { lazy, Suspense, useState, useEffect } from "react";
import { ConversationalHeader } from "./components/ConversationalHeader";
import { ConversationSidebar } from "./components/ConversationSidebar";
import { ConversationalChatArea } from "./components/ConversationalChatArea";
import { ContextPanel } from "./components/ContextPanel";
import { UploadModal } from "./components/UploadModal";
import { DataDashboard } from "./components/DataDashboard";
import { toast } from "sonner";
import { Toaster } from "./components/ui/sonner";
import {
  createConversation,
  deleteConversation as deletePersistedConversation,
  listConversations,
  listFiles,
  sendQueryStream,
  updateConversation,
  uploadFiles,
  FileInfo as APIFileInfo,
} from "./lib/client";
import type { AgentProgressEvent, PersistedConversation } from "./lib/client";
import type { AppPage, ChatMessage, DashboardPayload } from "./lib/appTypes";
import { useI18n } from "./lib/i18n";

const DevModePanel = lazy(() =>
  import("./components/DevModePanel").then((module) => ({ default: module.DevModePanel }))
);

interface FileInfo {
  id: string;
  name: string;
  size: string;
  rows: number;
  columns: number;
  preview: string[][];
}

interface Conversation {
  id: string;
  title: string;
  lastUpdated: string;
  messageCount: number;
  messages: ChatMessage[];
  activeFileIds: string[];
}

function displayTime(value: string, language: "zh" | "en") {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(language === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function hydrateConversation(conversation: PersistedConversation, language: "zh" | "en"): Conversation {
  return {
    id: conversation.id,
    title: conversation.title,
    lastUpdated: displayTime(conversation.updatedAt, language),
    messageCount: conversation.messageCount,
    activeFileIds: conversation.activeFileIds,
    messages: conversation.messages.map((message) => ({
      ...message,
      timestamp: displayTime(message.timestamp, language),
    })),
  };
}

export default function App() {
  const { language, t } = useI18n();
  const [isDark, setIsDark] = useState(false);
  const [showSidebar, setShowSidebar] = useState(() =>
    typeof window === "undefined" ? true : window.matchMedia("(min-width: 1024px)").matches
  );
  const [showPanel, setShowPanel] = useState(() =>
    typeof window === "undefined" ? true : window.matchMedia("(min-width: 1024px)").matches
  );
  const [showUploadModal, setShowUploadModal] = useState(false);
  
  const [allFiles, setAllFiles] = useState<FileInfo[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [agentProgressEvents, setAgentProgressEvents] = useState<AgentProgressEvent[]>([]);
  const [currentPage, setCurrentPage] = useState<AppPage>("analysis");
  const [dashboardPayload, setDashboardPayload] = useState<DashboardPayload | null>(null);
  const [isRestoring, setIsRestoring] = useState(true);

  const currentConversation = conversations.find((c) => c.id === currentConversationId);
  const activeFiles = allFiles.filter((f) => 
    currentConversation?.activeFileIds.includes(f.id)
  );

  // Apply theme
  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [isDark]);

  useEffect(() => {
    const desktopQuery = window.matchMedia("(min-width: 1024px)");
    const handleBreakpointChange = (event: MediaQueryListEvent) => {
      setShowSidebar(event.matches);
      setShowPanel(event.matches);
    };

    desktopQuery.addEventListener("change", handleBreakpointChange);
    return () => desktopQuery.removeEventListener("change", handleBreakpointChange);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listConversations(), listFiles()])
      .then(([savedConversations, savedFiles]) => {
        if (cancelled) return;
        const restored = savedConversations.map((conversation) => hydrateConversation(conversation, language));
        setConversations(restored);
        setAllFiles(savedFiles.map((file) => ({
          id: file.id,
          name: file.name || file.originalName || "unknown",
          size: file.size,
          rows: file.rows,
          columns: file.columns,
          preview: file.preview || [],
        })));
        const preferred = window.localStorage.getItem("datasays-current-conversation");
        const selected = restored.some((conversation) => conversation.id === preferred)
          ? preferred
          : restored[0]?.id || null;
        setCurrentConversationId(selected);
      })
      .catch((error) => {
        console.error("Failed to restore DataSays history", error);
        toast.error(language === "zh" ? "无法恢复历史分析，请检查后端服务" : "Could not restore analysis history");
      })
      .finally(() => {
        if (!cancelled) setIsRestoring(false);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (isRestoring) return;
    if (currentConversationId) {
      window.localStorage.setItem("datasays-current-conversation", currentConversationId);
    } else {
      window.localStorage.removeItem("datasays-current-conversation");
    }
    setDashboardPayload(null);
    setCurrentPage((page) => page === "dashboard" ? "analysis" : page);
  }, [currentConversationId, isRestoring]);

  const toggleTheme = () => setIsDark(!isDark);
  const toggleSidebar = () => setShowSidebar(!showSidebar);
  const togglePanel = () => setShowPanel(!showPanel);

  const handleNewChat = async () => {
    try {
      const created = await createConversation(t("newConversation"));
      const newConversation = hydrateConversation(created, language);
      setConversations((previous) => [newConversation, ...previous]);
      setCurrentConversationId(newConversation.id);
      if (window.innerWidth < 1024) setShowSidebar(false);
      toast.success(language === "zh" ? "已新建分析" : "New analysis started");
    } catch (error: any) {
      toast.error(error.message || (language === "zh" ? "新建分析失败" : "Failed to create analysis"));
    }
  };

  const handleSelectConversation = (id: string) => {
    setCurrentConversationId(id);
    if (window.innerWidth < 1024) setShowSidebar(false);
  };

  const handleRenameConversation = async (id: string, newTitle: string) => {
    try {
      await updateConversation(id, { title: newTitle });
      setConversations((previous) => previous.map((c) => (c.id === id ? { ...c, title: newTitle } : c)));
      toast.success(language === "zh" ? "分析已重命名" : "Analysis renamed");
    } catch (error: any) {
      toast.error(error.message || (language === "zh" ? "重命名失败" : "Rename failed"));
    }
  };

  const handleDeleteConversation = async (id: string) => {
    try {
      await deletePersistedConversation(id);
      setConversations((previous) => {
        const filtered = previous.filter((c) => c.id !== id);
        if (currentConversationId === id) setCurrentConversationId(filtered[0]?.id || null);
        return filtered;
      });
      toast.info(language === "zh" ? "分析已删除" : "Analysis deleted");
    } catch (error: any) {
      toast.error(error.message || (language === "zh" ? "删除失败" : "Delete failed"));
    }
  };

  const handleOpenUploadModal = () => {
    setShowUploadModal(true);
  };

  const handleCloseUploadModal = () => {
    setShowUploadModal(false);
  };

  const handleUploadFiles = async (files: File[]) => {
    try {
      // Upload files to backend
      const response = await uploadFiles(files);
      
      if (response.success && response.files.length > 0) {
        // Convert API response to frontend FileInfo format
        const newFiles: FileInfo[] = response.files.map((file: APIFileInfo) => ({
          id: file.id,
          name: file.name || file.originalName || 'unknown',
          size: file.size,
          rows: file.rows,
          columns: file.columns,
          preview: file.preview || [],
        }));

        setAllFiles((previous) => [...newFiles, ...previous.filter((file) => !newFiles.some((item) => item.id === file.id))]);
        
        // Create a new conversation if none exists
        if (!currentConversationId || conversations.length === 0) {
          const persisted = await createConversation(t("newConversation"), newFiles.map((file) => file.id));
          const newConversation = hydrateConversation(persisted, language);
          setConversations((previous) => [newConversation, ...previous]);
          setCurrentConversationId(newConversation.id);
          toast.success(language === "zh" ? "文件上传成功，已新建分析" : "Files uploaded in a new analysis");
        } else {
          // Add to current conversation's active files
          const nextIds = [...new Set([...(currentConversation?.activeFileIds || []), ...newFiles.map((file) => file.id)])];
          await updateConversation(currentConversationId, { activeFileIds: nextIds });
          setConversations((previous) => previous.map((c) => c.id === currentConversationId ? { ...c, activeFileIds: nextIds } : c));
          toast.success(language === "zh" ? `已添加 ${newFiles.length} 个文件` : `Added ${newFiles.length} file(s)`);
        }
        
        // Close the upload modal
        setShowUploadModal(false);
      }
    } catch (error: any) {
      console.error('Upload error:', error);
      toast.error(error.message || 'Failed to upload files');
      throw error;
    }
  };

  const handleAddFileToConversation = async (fileId: string) => {
    if (currentConversationId) {
      const nextIds = [...new Set([...(currentConversation?.activeFileIds || []), fileId])];
      await updateConversation(currentConversationId, { activeFileIds: nextIds });
      setConversations((previous) => previous.map((c) => c.id === currentConversationId ? { ...c, activeFileIds: nextIds } : c));
      const file = allFiles.find((f) => f.id === fileId);
      toast.success(`Added ${file?.name} to conversation`);
    }
  };

  const handleRemoveFileFromConversation = async (fileId: string) => {
    if (currentConversationId) {
      const nextIds = (currentConversation?.activeFileIds || []).filter((id) => id !== fileId);
      await updateConversation(currentConversationId, { activeFileIds: nextIds });
      setConversations((previous) => previous.map((c) => c.id === currentConversationId ? { ...c, activeFileIds: nextIds } : c));
      const file = allFiles.find((f) => f.id === fileId);
      toast.info(`Removed ${file?.name} from conversation`);
    }
  };

  const handleSendMessage = async (message: string, fileIds: string[], model?: string, promptStyle?: string) => {
    const filesUsed = allFiles
      .filter((f) => fileIds.includes(f.id))
      .map((f) => f.name);

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      type: "user",
      content: message,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      filesUsed,
    };

    if (currentConversationId) {
      const originalConversation = currentConversation;
      const nextTitle = originalConversation && (originalConversation.title === "New Conversation" || originalConversation.title === "新分析") && originalConversation.messages.length === 0
        ? message.slice(0, 40) + (message.length > 40 ? "..." : "")
        : originalConversation?.title;
      setConversations((previous) =>
        previous.map((c) => {
          if (c.id === currentConversationId) {
            // Auto-generate title from first message if it's still "New Conversation"
            const newTitle = (c.title === "New Conversation" || c.title === "新分析") && c.messages.length === 0
              ? message.slice(0, 40) + (message.length > 40 ? "..." : "")
              : c.title;
            
            return {
              ...c, 
              title: newTitle,
              messages: [...c.messages, userMessage],
              messageCount: c.messages.length + 1,
              lastUpdated: t("justNow"),
            };
          }
          return c;
        })
      );
      setIsLoading(true);
      setAgentProgressEvents([]);

      try {
        if (nextTitle && nextTitle !== originalConversation?.title) {
          await updateConversation(currentConversationId, { title: nextTitle });
        }
        const response = await sendQueryStream({
          question: message,
          fileIds: fileIds,
          project_id: new URLSearchParams(window.location.search).get("project_id") || undefined,
          model,
          prompt_style: promptStyle || "zero",
          mode: "agent",
          conversationId: currentConversationId,
          userMessageId: userMessage.id,
        }, (event) => {
          setAgentProgressEvents((previous) => {
            if (!event.node) return previous;
            const existingIndex = previous.findIndex((item) => item.id === event.id);
            if (existingIndex < 0) return [...previous, event];
            const next = [...previous];
            next[existingIndex] = event;
            return next;
          });
        });

        console.log("FULL API RESPONSE:", response);
        console.log("sandboxResponse:", response.sandboxResponse);
        console.log("thinking_process:", response.sandboxResponse?.thinking_process);

        const aiMessage: ChatMessage = {
          id: crypto.randomUUID(),
          type: "ai",
          content: "", // Not used in dual mode
          timestamp: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
          llmResponse: response.llmResponse,
          sandboxResponse: response.sandboxResponse,
        };

        setConversations((prev) =>
          prev.map((c) =>
            c.id === currentConversationId
              ? { 
                  ...c, 
                  messages: [...c.messages, aiMessage],
                  messageCount: c.messages.length + 1,
                }
              : c
          )
        );
      } catch (error: any) {
        console.error('Query error:', error);
        toast.error(error.message || 'Failed to process query');
        
        // Add error message to conversation
        const errorMessage: ChatMessage = {
          id: crypto.randomUUID(),
          type: "ai",
          content: "",
          timestamp: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
          llmResponse: {
            content: `Error: ${error.message || 'Failed to get response'}`,
            status: "error",
          },
          sandboxResponse: {
            content: `Error: ${error.message || 'Failed to get response'}`,
            status: "error",
          },
        };

        setConversations((prev) =>
          prev.map((c) =>
            c.id === currentConversationId
              ? { 
                  ...c, 
                  messages: [...c.messages, errorMessage],
                  messageCount: c.messages.length + 1,
                }
              : c
          )
        );
      } finally {
        setIsLoading(false);
      }
    }
  };


  return (
    <div className="h-[100dvh] flex flex-col bg-gray-50 dark:bg-gray-950 overflow-hidden">
      <ConversationalHeader
        currentPage={currentPage}
        onNavigate={setCurrentPage}
        isDark={isDark}
        toggleTheme={toggleTheme}
        onUpload={handleOpenUploadModal}
        showPanel={showPanel}
        togglePanel={togglePanel}
        showSidebar={showSidebar}
        toggleSidebar={toggleSidebar}
      />
      <div className="relative flex-1 flex w-full min-h-0 overflow-hidden">
        {currentPage === "analysis" && (showSidebar || showPanel) && (
          <button
            type="button"
            aria-label="Close open panel"
            className="fixed inset-x-0 bottom-0 top-16 z-40 bg-slate-950/30 backdrop-blur-[2px] lg:hidden"
            onClick={() => {
              setShowSidebar(false);
              setShowPanel(false);
            }}
          />
        )}
        {/* Left Sidebar - Fixed width */}
        {currentPage === "analysis" && showSidebar && (
          <div className="fixed bottom-0 left-0 top-16 z-50 flex lg:static lg:z-auto">
            <ConversationSidebar
              conversations={conversations}
              currentConversationId={currentConversationId}
              onNewChat={handleNewChat}
              onSelectConversation={handleSelectConversation}
              onRenameConversation={handleRenameConversation}
              onDeleteConversation={handleDeleteConversation}
              onClose={toggleSidebar}
            />
          </div>
        )}
        {/* Middle Chat Area - Flexible width */}
        {currentPage === "comparison" ? (
          <Suspense fallback={<div className="flex flex-1 items-center justify-center text-sm text-gray-500">{t("loadingDeveloper")}</div>}>
            <DevModePanel
              activeFiles={activeFiles.map(f => ({ id: f.id, name: f.name }))}
              onExit={() => setCurrentPage("analysis")}
            />
          </Suspense>
        ) : currentPage === "dashboard" ? (
          <DataDashboard payload={dashboardPayload} onOpenAnalysis={() => setCurrentPage("analysis")} />
        ) : (
          <ConversationalChatArea
            messages={currentConversation?.messages || []}
            onSendMessage={handleSendMessage}
            onOpenDashboard={(payload) => {
              setDashboardPayload(payload);
              setCurrentPage("dashboard");
            }}
            isLoading={isLoading || isRestoring}
            progressEvents={agentProgressEvents}
            activeFiles={activeFiles.map(f => ({ id: f.id, name: f.name }))}
            onUpload={handleOpenUploadModal}
          />
        )}
        {/* Right Context Panel - Fixed width */}
        {currentPage === "analysis" && showPanel && (
          <div className="fixed bottom-0 right-0 top-16 z-50 flex lg:static lg:z-auto">
            <ContextPanel
              activeFiles={activeFiles}
              recentFiles={allFiles}
              onAddFile={handleAddFileToConversation}
              onRemoveFile={handleRemoveFileFromConversation}
              onUploadNew={handleOpenUploadModal}
            />
          </div>
        )}
      </div>
      
      <UploadModal
        open={showUploadModal}
        onClose={handleCloseUploadModal}
        onUpload={handleUploadFiles}
      />
      
      <Toaster />
    </div>
  );
}
