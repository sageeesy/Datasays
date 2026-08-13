import { Plus, MessageSquare, MoreVertical, Pencil, Trash2, PanelLeftClose } from "lucide-react";
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { useState } from "react";
import { Input } from "./ui/input";
import { useI18n } from "../lib/i18n";

interface Conversation {
  id: string;
  title: string;
  lastUpdated: string;
  messageCount: number;
}

interface ConversationSidebarProps {
  conversations: Conversation[];
  currentConversationId: string | null;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onRenameConversation: (id: string, newTitle: string) => void;
  onDeleteConversation: (id: string) => void;
  onClose: () => void;
}

export function ConversationSidebar({
  conversations,
  currentConversationId,
  onNewChat,
  onSelectConversation,
  onRenameConversation,
  onDeleteConversation,
  onClose,
}: ConversationSidebarProps) {
  const { t } = useI18n();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const handleStartEdit = (conversation: Conversation) => {
    setEditingId(conversation.id);
    setEditValue(conversation.title);
  };

  const handleSaveEdit = (id: string) => {
    if (editValue.trim()) {
      onRenameConversation(id, editValue.trim());
    }
    setEditingId(null);
  };

  const handleKeyPress = (e: React.KeyboardEvent, id: string) => {
    if (e.key === "Enter") {
      handleSaveEdit(id);
    } else if (e.key === "Escape") {
      setEditingId(null);
    }
  };

  return (
    <aside className="flex h-full w-[min(18rem,88vw)] shrink-0 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900 lg:w-[260px]" aria-label={t("conversations")}>
      <div className="border-b border-gray-200 p-3 dark:border-gray-800">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm text-gray-600 dark:text-gray-400">{t("conversations")}</h3>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={onClose}
            aria-label={t("closeConversations")}
            title={t("closeConversations")}
          >
            <PanelLeftClose className="h-4 w-4" />
          </Button>
        </div>
        <Button
          onClick={onNewChat}
          className="w-full gap-2 bg-blue-600 hover:bg-blue-700"
          size="sm"
        >
          <Plus className="h-4 w-4" />
          {t("newChat")}
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {conversations.length === 0 ? (
            <div className="text-center py-8 px-4">
              <MessageSquare className="h-8 w-8 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
              <p className="text-xs text-gray-400 dark:text-gray-500">
                {t("noConversations")}
              </p>
            </div>
          ) : (
            conversations.map((conversation) => (
              <div
                key={conversation.id}
                className={`group relative rounded-lg transition-colors ${
                  currentConversationId === conversation.id
                    ? "bg-blue-50 dark:bg-blue-900/20"
                    : "hover:bg-gray-50 dark:hover:bg-gray-800"
                }`}
              >
                {editingId === conversation.id ? (
                  <div className="p-2">
                    <Input
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onBlur={() => handleSaveEdit(conversation.id)}
                      onKeyDown={(e) => handleKeyPress(e, conversation.id)}
                      className="h-7 text-sm"
                      autoFocus
                    />
                  </div>
                ) : (
                  <button
                    onClick={() => onSelectConversation(conversation.id)}
                      className="w-full rounded-lg p-2 pr-8 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                  >
                    <div className="flex items-start gap-2">
                      <MessageSquare className={`h-4 w-4 mt-0.5 flex-shrink-0 ${
                        currentConversationId === conversation.id
                          ? "text-blue-600 dark:text-blue-400"
                          : "text-gray-400 dark:text-gray-500"
                      }`} />
                      <div className="flex-1 min-w-0">
                        <p className={`text-sm truncate ${
                          currentConversationId === conversation.id
                            ? "text-blue-900 dark:text-blue-100"
                            : "text-gray-900 dark:text-white"
                        }`}>
                          {conversation.title}
                        </p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            {conversation.lastUpdated}
                          </p>
                          <span className="text-xs text-gray-400 dark:text-gray-500">
                            •
                          </span>
                          <p className="text-xs text-gray-400 dark:text-gray-500">
                            {conversation.messageCount} {t("messages")}
                          </p>
                        </div>
                      </div>
                    </div>
                  </button>
                )}

                {editingId !== conversation.id && (
                  <div className="absolute right-1 top-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          aria-label={`Actions for ${conversation.title}`}
                        >
                          <MoreVertical className="h-3.5 w-3.5" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleStartEdit(conversation)}>
                          <Pencil className="h-3.5 w-3.5 mr-2" />
                          {t("rename")}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => onDeleteConversation(conversation.id)}
                          className="text-red-600 dark:text-red-400"
                        >
                          <Trash2 className="h-3.5 w-3.5 mr-2" />
                          {t("delete")}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}
