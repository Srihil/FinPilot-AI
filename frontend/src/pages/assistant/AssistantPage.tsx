import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Send, Plus, Bot, User, Trash2, MessageSquare, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { assistantApi } from '../../api/endpoints';
import { Button } from '../../components/ui/button';
import { Skeleton } from '../../components/ui/skeleton';
import { formatRelativeTime } from '../../utils/format';
import type { Conversation, Message } from '../../types';
import { cn } from '../../utils/cn';
import { toast } from '../../components/ui/use-toast';

const SUGGESTED_QUESTIONS = [
  'What was our revenue this month?',
  'Show me overdue invoices',
  'Who are our top 5 customers?',
  'What are our biggest expense categories?',
  'How does this month compare to last month?',
  'What is our current outstanding receivables?',
];

function ErrorBox({ error }: { error: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 rounded-lg border border-red-200 bg-red-50 text-xs overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-1.5 px-3 py-2 text-red-700 font-medium hover:bg-red-100 transition-colors text-left"
      >
        <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
        <span className="flex-1">Provider error — click to {open ? 'hide' : 'show'} details</span>
        {open ? <ChevronUp className="w-3.5 h-3.5 shrink-0" /> : <ChevronDown className="w-3.5 h-3.5 shrink-0" />}
      </button>
      {open && (
        <pre className="px-3 py-2 text-red-800 whitespace-pre-wrap break-all border-t border-red-200 bg-red-50 font-mono leading-relaxed">
          {error}
        </pre>
      )}
    </div>
  );
}

export default function AssistantPage() {
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [localMessages, setLocalMessages] = useState<Message[]>([]);
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const queryClient = useQueryClient();

  const { data: conversations, isLoading: convsLoading } = useQuery({
    queryKey: ['conversations'],
    queryFn: assistantApi.listConversations,
    retry: 1,
  });

  const { data: messages } = useQuery({
    queryKey: ['messages', activeConversationId],
    queryFn: () => assistantApi.getMessages(activeConversationId!),
    enabled: !!activeConversationId,
  });

  const createConvMutation = useMutation({
    mutationFn: assistantApi.createConversation,
    onSuccess: (conv) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      setActiveConversationId(conv.id);
      setLocalMessages([]);
    },
  });

  const deleteConvMutation = useMutation({
    mutationFn: assistantApi.deleteConversation,
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      if (activeConversationId === deletedId) {
        setActiveConversationId(null);
        setLocalMessages([]);
      }
    },
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [localMessages]);

  useEffect(() => {
    if (messages) setLocalMessages(messages);
  }, [messages]);

  const sendMessage = async (content: string) => {
    if (!content.trim()) return;
    if (!activeConversationId) {
      // Create conversation first
      const conv = await assistantApi.createConversation();
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      setActiveConversationId(conv.id);

      const userMsg: Message = {
        id: Date.now().toString(),
        conversation_id: conv.id,
        role: 'user',
        content,
        created_at: new Date().toISOString(),
      };
      setLocalMessages([userMsg]);
      setInputValue('');
      setIsSending(true);

      try {
        const response = await assistantApi.sendMessage(conv.id, content);
        setLocalMessages(prev => [...prev, response]);
        queryClient.invalidateQueries({ queryKey: ['conversations'] });
      } catch {
        toast({ title: 'Failed to send message', variant: 'destructive' });
      } finally {
        setIsSending(false);
      }
      return;
    }

    const userMsg: Message = {
      id: Date.now().toString(),
      conversation_id: activeConversationId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };
    setLocalMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setIsSending(true);

    try {
      const response = await assistantApi.sendMessage(activeConversationId, content);
      setLocalMessages(prev => [...prev.filter(m => m.id !== userMsg.id), userMsg, response]);
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    } catch {
      toast({ title: 'Failed to send message', variant: 'destructive' });
      setLocalMessages(prev => prev.filter(m => m.id !== userMsg.id));
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(inputValue);
    }
  };

  return (
    <div className="flex h-[calc(100vh-9rem)] rounded-xl border border-slate-200 bg-white overflow-hidden">
      {/* Conversations Sidebar */}
      <div className="w-72 border-r border-slate-200 flex flex-col shrink-0">
        <div className="p-4 border-b border-slate-200">
          <Button
            className="w-full"
            onClick={() => createConvMutation.mutate('New Conversation')}
            loading={createConvMutation.isPending}
          >
            <Plus className="w-4 h-4 mr-2" />
            New Conversation
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {convsLoading ? (
            <div className="p-4 space-y-2">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-14" />)}
            </div>
          ) : conversations?.length === 0 || !conversations ? (
            <div className="p-6 text-center text-slate-400 text-sm">
              <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-40" />
              No conversations yet
            </div>
          ) : (
            <div className="p-2 space-y-1">
              {conversations.map((conv: Conversation) => (
                <div
                  key={conv.id}
                  className={cn(
                    "group flex items-center gap-1 rounded-lg transition-colors",
                    activeConversationId === conv.id
                      ? "bg-indigo-50 border border-indigo-200"
                      : "hover:bg-slate-50"
                  )}
                >
                  {/* Main clickable area */}
                  <button
                    onClick={() => { setActiveConversationId(conv.id); setLocalMessages([]); }}
                    className="flex-1 min-w-0 text-left px-3 py-2.5"
                  >
                    <p className={cn(
                      "text-sm font-medium truncate",
                      activeConversationId === conv.id ? "text-indigo-700" : "text-slate-700"
                    )}>
                      {conv.title || 'New conversation'}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">{formatRelativeTime(conv.updated_at)}</p>
                  </button>

                  {/* Delete button — visible on hover or when active */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteConvMutation.mutate(conv.id);
                    }}
                    disabled={deleteConvMutation.isPending}
                    title="Delete conversation"
                    className={cn(
                      "shrink-0 mr-1.5 w-6 h-6 flex items-center justify-center rounded-md transition-all",
                      "text-slate-400 hover:text-red-500 hover:bg-red-50",
                      "opacity-0 group-hover:opacity-100",
                      activeConversationId === conv.id && "opacity-60 group-hover:opacity-100",
                      deleteConvMutation.isPending && deleteConvMutation.variables === conv.id && "opacity-100"
                    )}
                  >
                    {deleteConvMutation.isPending && deleteConvMutation.variables === conv.id ? (
                      <div className="w-3 h-3 border border-slate-400 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <Trash2 className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Chat header */}
        <div className="h-14 border-b border-slate-200 px-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
              <Bot className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold text-slate-900">FinPilot Assistant</span>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {localMessages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center mb-4">
                <Bot className="w-8 h-8 text-white" />
              </div>
              <h3 className="text-xl font-semibold text-slate-900 mb-2">Ask me anything about your finances</h3>
              <p className="text-slate-500 text-sm mb-8 max-w-md">
                I can analyze your transactions, generate reports, find insights, and answer financial questions.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => sendMessage(q)}
                    className="text-left px-4 py-3 rounded-xl border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50 transition-all text-sm text-slate-700 hover:text-indigo-700 group"
                  >
                    <span className="text-indigo-500 mr-1 group-hover:mr-2 transition-all">&rsaquo;</span>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {localMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={cn(
                    "flex gap-3 animate-fade-in",
                    msg.role === 'user' ? "flex-row-reverse" : "flex-row"
                  )}
                >
                  <div className={cn(
                    "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
                    msg.role === 'user' ? "bg-indigo-600" : "bg-gradient-to-br from-indigo-500 to-violet-600"
                  )}>
                    {msg.role === 'user'
                      ? <User className="w-4 h-4 text-white" />
                      : <Bot className="w-4 h-4 text-white" />
                    }
                  </div>
                  <div className={cn(
                    "max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
                    msg.role === 'user'
                      ? "bg-indigo-600 text-white rounded-tr-sm"
                      : "bg-white border border-slate-200 shadow-sm text-slate-800 rounded-tl-sm"
                  )}>
                    {msg.role === 'user' ? (
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    ) : (
                      <>
                        <div className="prose prose-sm prose-slate max-w-none
                          prose-headings:font-semibold prose-headings:text-slate-900 prose-headings:mt-3 prose-headings:mb-1
                          prose-p:my-1.5 prose-p:leading-relaxed
                          prose-strong:font-semibold prose-strong:text-slate-900
                          prose-em:text-slate-600
                          prose-ul:my-1.5 prose-ul:space-y-0.5 prose-li:my-0
                          prose-code:bg-slate-100 prose-code:px-1 prose-code:rounded prose-code:text-xs prose-code:text-indigo-700 prose-code:font-mono
                          [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                          </ReactMarkdown>
                        </div>
                        {msg.error && <ErrorBox error={msg.error} />}
                      </>
                    )}
                    <div className={cn("flex items-center gap-1.5 mt-2", msg.role === 'user' ? "justify-end" : "justify-start")}>
                      <span className={cn("text-xs", msg.role === 'user' ? "text-indigo-200" : "text-slate-400")}>
                        {formatRelativeTime(msg.created_at)}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
              {isSending && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shrink-0">
                    <Bot className="w-4 h-4 text-white" />
                  </div>
                  <div className="bg-slate-100 rounded-2xl rounded-tl-sm px-4 py-3">
                    <div className="flex gap-1 items-center h-5">
                      <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-slate-200 p-4">
          <div className="flex gap-3 items-end bg-slate-50 border border-slate-200 rounded-xl p-3 focus-within:border-indigo-300 focus-within:ring-2 focus-within:ring-indigo-100 transition-all">
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about revenue, invoices, customers..."
              rows={1}
              className="flex-1 bg-transparent resize-none outline-none text-sm text-slate-900 placeholder:text-slate-400 max-h-32"
              style={{ lineHeight: '1.5' }}
            />
            <Button
              onClick={() => sendMessage(inputValue)}
              disabled={!inputValue.trim() || isSending}
              size="icon"
              className="shrink-0"
            >
              <Send className="w-4 h-4" />
            </Button>
          </div>
          <p className="text-xs text-slate-400 mt-2 text-center">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </div>
    </div>
  );
}
