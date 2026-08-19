import { useState, useRef, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Send, Plus, Bot, User, Trash2, MessageSquare,
  ChevronDown, ChevronUp, AlertTriangle, Loader2, Database,
  Sparkles,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { assistantApi } from '../../api/endpoints';
import { Button } from '../../components/ui/button';
import { Skeleton } from '../../components/ui/skeleton';
import { formatRelativeTime } from '../../utils/format';
import type { Conversation, Message } from '../../types';
import { cn } from '../../utils/cn';
import { toast } from '../../components/ui/use-toast';

// ── Placeholder ID used while streaming ──────────────────────────────────────
const STREAMING_ID = '__streaming__';

const SUGGESTED_QUESTIONS = [
  'What was our revenue this month?',
  'Show me all unpaid invoices above ₹50,000',
  'Who are our top 5 customers by revenue?',
  'Which expense categories cost the most this year?',
  'List customers with outstanding dues over ₹1 lakh',
  "Compare this month's profit to last month",
  'Show me every Sales invoice in August 2026',
  'What is our total inventory value?',
];

// ── Error details box ─────────────────────────────────────────────────────────
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
        <pre className="px-3 py-2 text-red-800 whitespace-pre-wrap break-all border-t border-red-200 font-mono leading-relaxed">
          {error}
        </pre>
      )}
    </div>
  );
}

// ── Animated status pill shown while a tool is executing ─────────────────────
function StatusPill({ text }: { text: string }) {
  const isDb = text.toLowerCase().includes('queri') || text.toLowerCase().includes('database');
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-50 border border-indigo-100 w-fit">
      {isDb
        ? <Database className="w-3 h-3 text-indigo-500 shrink-0 animate-pulse" />
        : <Loader2 className="w-3 h-3 text-indigo-500 shrink-0 animate-spin" />
      }
      <span className="text-xs font-medium text-indigo-700">{text}</span>
    </div>
  );
}

// ── Blinking cursor shown at the end of a streaming message ──────────────────
function StreamCursor() {
  return (
    <span className="inline-block w-0.5 h-4 bg-indigo-500 ml-0.5 align-text-bottom animate-[blink_1s_step-end_infinite]" />
  );
}

// ── Single message bubble ─────────────────────────────────────────────────────
function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user';
  const isStreaming = msg.isStreaming === true;

  return (
    <div className={cn('flex gap-3 animate-fade-in', isUser ? 'flex-row-reverse' : 'flex-row')}>
      {/* Avatar */}
      <div className={cn(
        'w-8 h-8 rounded-full flex items-center justify-center shrink-0',
        isUser ? 'bg-indigo-600' : 'bg-gradient-to-br from-indigo-500 to-violet-600',
      )}>
        {isUser
          ? <User className="w-4 h-4 text-white" />
          : <Bot className="w-4 h-4 text-white" />
        }
      </div>

      {/* Bubble */}
      <div className={cn(
        'max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-relaxed',
        isUser
          ? 'bg-indigo-600 text-white rounded-tr-sm'
          : 'bg-white border border-slate-200 shadow-sm text-slate-800 rounded-tl-sm',
      )}>
        {isUser ? (
          <p className="whitespace-pre-wrap">{msg.content}</p>
        ) : (
          <>
            {/* Status pill while tool is executing */}
            {isStreaming && msg.statusText && !msg.content && (
              <div className="py-1">
                <StatusPill text={msg.statusText} />
              </div>
            )}

            {/* Growing response text */}
            {msg.content ? (
              <div className="prose prose-sm prose-slate max-w-none
                prose-headings:font-semibold prose-headings:text-slate-900 prose-headings:mt-3 prose-headings:mb-1
                prose-p:my-1.5 prose-p:leading-relaxed
                prose-strong:font-semibold prose-strong:text-slate-900
                prose-ul:my-1.5 prose-ul:space-y-0.5 prose-li:my-0
                prose-table:text-xs prose-th:bg-slate-50 prose-th:font-semibold
                prose-code:bg-slate-100 prose-code:px-1 prose-code:rounded prose-code:text-xs
                prose-code:text-indigo-700 prose-code:font-mono
                [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.content}
                </ReactMarkdown>
                {isStreaming && <StreamCursor />}
              </div>
            ) : isStreaming && !msg.statusText ? (
              /* Dots while waiting for first token */
              <div className="flex gap-1 items-center h-5 py-1">
                <div className="w-2 h-2 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            ) : null}

            {msg.error && <ErrorBox error={msg.error} />}
          </>
        )}

        {/* Timestamp */}
        {!isStreaming && (
          <div className={cn('flex items-center gap-1.5 mt-2', isUser ? 'justify-end' : 'justify-start')}>
            <span className={cn('text-xs', isUser ? 'text-indigo-200' : 'text-slate-400')}>
              {formatRelativeTime(msg.created_at)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function AssistantPage() {
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [localMessages, setLocalMessages] = useState<Message[]>([]);
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const queryClient = useQueryClient();

  // ── Data fetching ───────────────────────────────────────────────────────────
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

  useEffect(() => { if (messages) setLocalMessages(messages); }, [messages]);
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [localMessages]);

  // ── Mutations ───────────────────────────────────────────────────────────────
  const createConvMutation = useMutation({
    mutationFn: () => assistantApi.createConversation('New Conversation'),
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

  // ── Streaming send ──────────────────────────────────────────────────────────
  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isSending) return;
    setIsSending(true);
    setInputValue('');

    // Ensure we have a conversation
    let convId = activeConversationId;
    if (!convId) {
      try {
        const conv = await assistantApi.createConversation('New Conversation');
        queryClient.invalidateQueries({ queryKey: ['conversations'] });
        setActiveConversationId(conv.id);
        convId = conv.id;
        setLocalMessages([]);
      } catch {
        toast({ title: 'Could not create conversation', variant: 'destructive' });
        setIsSending(false);
        return;
      }
    }

    // Optimistic user message
    const userMsg: Message = {
      id: `user-${Date.now()}`,
      conversation_id: convId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };

    // Placeholder AI message (streaming state)
    const placeholder: Message = {
      id: STREAMING_ID,
      conversation_id: convId,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
      isStreaming: true,
      statusText: undefined,
    };

    setLocalMessages(prev => [...prev, userMsg, placeholder]);

    try {
      await assistantApi.streamMessage(
        convId,
        content,

        // onStatus — tool executing
        (statusText) => {
          setLocalMessages(prev =>
            prev.map(m => m.id === STREAMING_ID ? { ...m, statusText, content: '' } : m),
          );
        },

        // onToken — append text
        (token) => {
          setLocalMessages(prev =>
            prev.map(m =>
              m.id === STREAMING_ID
                ? { ...m, content: m.content + token, statusText: undefined }
                : m,
            ),
          );
        },

        // onDone — replace placeholder with real message
        (finalMsg) => {
          setLocalMessages(prev =>
            prev.map(m => m.id === STREAMING_ID ? { ...finalMsg, isStreaming: false } : m),
          );
          queryClient.invalidateQueries({ queryKey: ['conversations'] });
          queryClient.invalidateQueries({ queryKey: ['messages', convId] });
        },

        // onError
        (errText) => {
          setLocalMessages(prev =>
            prev.map(m =>
              m.id === STREAMING_ID
                ? { ...m, isStreaming: false, content: m.content || 'Something went wrong.', error: errText }
                : m,
            ),
          );
          toast({ title: 'AI error', description: errText, variant: 'destructive' });
        },
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLocalMessages(prev =>
        prev.map(m =>
          m.id === STREAMING_ID
            ? { ...m, isStreaming: false, content: 'Connection error.', error: msg }
            : m,
        ),
      );
      toast({ title: 'Failed to send message', description: msg, variant: 'destructive' });
    } finally {
      setIsSending(false);
    }
  }, [activeConversationId, isSending, queryClient]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(inputValue); }
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-[calc(100vh-9rem)] rounded-xl border border-slate-200 bg-white overflow-hidden">

      {/* ── Conversation sidebar ─────────────────────────────────────────── */}
      <div className="w-72 border-r border-slate-200 flex flex-col shrink-0">
        <div className="p-4 border-b border-slate-200">
          <Button
            className="w-full gap-2"
            onClick={() => createConvMutation.mutate()}
            disabled={createConvMutation.isPending}
          >
            <Plus className="w-4 h-4" />
            New Conversation
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {convsLoading ? (
            <div className="p-4 space-y-2">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-14" />)}
            </div>
          ) : !conversations?.length ? (
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
                    'group flex items-center gap-1 rounded-lg transition-colors',
                    activeConversationId === conv.id
                      ? 'bg-indigo-50 border border-indigo-200'
                      : 'hover:bg-slate-50',
                  )}
                >
                  <button
                    onClick={() => { setActiveConversationId(conv.id); setLocalMessages([]); }}
                    className="flex-1 min-w-0 text-left px-3 py-2.5"
                  >
                    <p className={cn(
                      'text-sm font-medium truncate',
                      activeConversationId === conv.id ? 'text-indigo-700' : 'text-slate-700',
                    )}>
                      {conv.title || 'New conversation'}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">{formatRelativeTime(conv.updated_at)}</p>
                  </button>

                  <button
                    onClick={(e) => { e.stopPropagation(); deleteConvMutation.mutate(conv.id); }}
                    disabled={deleteConvMutation.isPending}
                    title="Delete conversation"
                    className={cn(
                      'shrink-0 mr-1.5 w-6 h-6 flex items-center justify-center rounded-md transition-all',
                      'text-slate-400 hover:text-red-500 hover:bg-red-50',
                      'opacity-0 group-hover:opacity-100',
                      activeConversationId === conv.id && 'opacity-60 group-hover:opacity-100',
                    )}
                  >
                    {deleteConvMutation.isPending && deleteConvMutation.variables === conv.id
                      ? <div className="w-3 h-3 border border-slate-400 border-t-transparent rounded-full animate-spin" />
                      : <Trash2 className="w-3.5 h-3.5" />
                    }
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Chat area ────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* Header */}
        <div className="h-14 border-b border-slate-200 px-6 flex items-center gap-3">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
            <Bot className="w-4 h-4 text-white" />
          </div>
          <div>
            <span className="font-semibold text-slate-900 text-sm">FinPilot Assistant</span>
            <p className="text-xs text-slate-400 leading-none mt-0.5">Full database access · Powered by Groq</p>
          </div>
          <div className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200">
            <Sparkles className="w-3 h-3 text-emerald-600" />
            <span className="text-xs font-medium text-emerald-700">Ask anything</span>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {localMessages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center mb-4 shadow-lg">
                <Bot className="w-8 h-8 text-white" />
              </div>
              <h3 className="text-xl font-semibold text-slate-900 mb-2">Ask me anything about your finances</h3>
              <p className="text-slate-500 text-sm mb-2 max-w-md">
                I have full read access to your database — invoices, customers, expenses, vouchers, inventory, and more.
              </p>
              <p className="text-slate-400 text-xs mb-8 max-w-sm">
                Ask specific questions like "show all unpaid invoices above ₹50,000" — I'll query the database directly.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-xl">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => sendMessage(q)}
                    disabled={isSending}
                    className="text-left px-4 py-3 rounded-xl border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50 transition-all text-sm text-slate-700 hover:text-indigo-700 group disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span className="text-indigo-400 mr-1.5 group-hover:mr-2 transition-all">›</span>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {localMessages.map((msg) => (
                <MessageBubble key={msg.id} msg={msg} />
              ))}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-slate-200 p-4">
          <div className={cn(
            'flex gap-3 items-end bg-slate-50 border rounded-xl p-3 transition-all',
            isSending
              ? 'border-indigo-200 ring-2 ring-indigo-100'
              : 'border-slate-200 focus-within:border-indigo-300 focus-within:ring-2 focus-within:ring-indigo-100',
          )}>
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about revenue, invoices, customers, or anything in your data…"
              rows={1}
              disabled={isSending}
              className="flex-1 bg-transparent resize-none outline-none text-sm text-slate-900 placeholder:text-slate-400 max-h-32 disabled:opacity-60"
              style={{ lineHeight: '1.5' }}
            />
            <Button
              onClick={() => sendMessage(inputValue)}
              disabled={!inputValue.trim() || isSending}
              size="icon"
              className="shrink-0"
            >
              {isSending
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <Send className="w-4 h-4" />
              }
            </Button>
          </div>
          <p className="text-xs text-slate-400 mt-2 text-center">
            Enter to send · Shift+Enter for new line · Full database access with guardrails
          </p>
        </div>
      </div>
    </div>
  );
}
