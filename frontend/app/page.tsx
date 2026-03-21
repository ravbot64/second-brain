"use client";

import { useState, useRef, useEffect } from "react";
import KnowledgeModal from "./components/KnowledgeModal";
import AboutModal from "./components/AboutModal";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

type Message = {
  id: string;
  role: string;
  content: string;
  sources?: { score: number; source?: string }[];
  timestamp: Date;
};

type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
};

type AuthUser = {
  id: string;
  email: string;
  is_guest: boolean;
  full_name?: string;
  bio?: string;
};

const SUGGESTED_PROMPTS = [
  "What are the main topics in my knowledge base?",
  "Summarize what I know about machine learning",
  "Find notes related to productivity or planning",
  "What have I written about most recently?",
];

// Brain icon used in avatars
const BrainIcon = ({ size = 13 }: { size?: number }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z" />
    <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z" />
  </svg>
);

export default function Home() {
  const makeConv = (): Conversation => ({
    id: crypto.randomUUID(),
    title: "New conversation",
    messages: [],
    createdAt: new Date(),
  });

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [historyReady, setHistoryReady] = useState(false);

  const ensureConversation = () => {
    const first = makeConv();
    setConversations([first]);
    setActiveId(first.id);
  };

  const hydrateConversation = (raw: {
    id: string;
    title: string;
    created_at?: string;
    messages?: Array<{
      id: string;
      role: string;
      content: string;
      sources?: { score: number; source?: string }[];
      timestamp?: string;
    }>;
  }): Conversation => ({
    id: raw.id,
    title: raw.title || "New conversation",
    createdAt: raw.created_at ? new Date(raw.created_at) : new Date(),
    messages: (raw.messages || []).map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      sources: m.sources,
      timestamp: m.timestamp ? new Date(m.timestamp) : new Date(),
    })),
  });

  const createRemoteConversation = async (): Promise<Conversation | null> => {
    const res = await authFetch(`${API_BASE_URL}/api/history/conversations`, {
      method: "POST",
    });
    if (res.status === 401) {
      logout();
      return null;
    }
    if (!res.ok) {
      throw new Error("Failed to create conversation");
    }
    const data = await res.json();
    return hydrateConversation(data);
  };

  const activeConversation = conversations.find((c) => c.id === activeId);
  const messages = activeConversation?.messages ?? [];

  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isAboutOpen, setIsAboutOpen] = useState(false);
  const [documentCount, setDocumentCount] = useState(0);
  const [isKbLoading, setIsKbLoading] = useState(true);
  const [isKbSyncing, setIsKbSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [mobileView, setMobileView] = useState<"history" | "chat" | "kb">("chat");
  const [token, setToken] = useState("");
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authFullName, setAuthFullName] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [profileName, setProfileName] = useState("");
  const [profileBio, setProfileBio] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileDeleting, setProfileDeleting] = useState(false);
  const [isDeleteSheetOpen, setIsDeleteSheetOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isCreatingNewChat, setIsCreatingNewChat] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeIdRef = useRef(activeId);
  const newChatClickLockRef = useRef(false);
  useEffect(() => { activeIdRef.current = activeId; }, [activeId]);

  const showError = (msg: string) => {
    if (errorTimeoutRef.current) clearTimeout(errorTimeoutRef.current);
    setError(msg);
    errorTimeoutRef.current = setTimeout(() => setError(null), 5000);
  };

  const authFetch = (url: string, init?: RequestInit) => {
    const headers = new Headers(init?.headers || {});
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(url, { ...init, headers });
  };

  const persistSession = (nextToken: string, user: AuthUser) => {
    setToken(nextToken);
    setAuthUser(user);
    localStorage.setItem("sb_token", nextToken);
    localStorage.setItem("sb_user", JSON.stringify(user));
  };

  const logout = () => {
    setToken("");
    setAuthUser(null);
    setHistoryReady(false);
    localStorage.removeItem("sb_token");
    localStorage.removeItem("sb_user");
    ensureConversation();
  };

  useEffect(() => {
    const storedToken = localStorage.getItem("sb_token");
    const storedUser = localStorage.getItem("sb_user");
    if (!storedToken || !storedUser) return;
    try {
      const parsed = JSON.parse(storedUser) as AuthUser;
      setToken(storedToken);
      setAuthUser(parsed);
      setProfileName(parsed.full_name || "");
      setProfileBio(parsed.bio || "");
    } catch {
      localStorage.removeItem("sb_token");
      localStorage.removeItem("sb_user");
    }
  }, []);

  useEffect(() => {
    if (!authUser || !token) {
      setHistoryReady(false);
      return;
    }

    (async () => {
      try {
        const res = await authFetch(`${API_BASE_URL}/api/history`);
        if (res.status === 401) {
          logout();
          return;
        }
        if (!res.ok) throw new Error("Failed to load history");
        const data = await res.json();
        const restored = (Array.isArray(data) ? data : []).map(hydrateConversation);

        if (!restored.length) {
          const created = await createRemoteConversation();
          if (!created) return;
          setConversations([created]);
          setActiveId(created.id);
          setHistoryReady(true);
          return;
        }

        setConversations(restored);
        setActiveId(restored[0].id);
        setHistoryReady(true);
      } catch (e) {
        console.error(e);
        showError("Failed to load chat history");
        ensureConversation();
        setHistoryReady(true);
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authUser?.id, token]);

  const checkDocumentCount = async (silent = false) => {
    if (!token) return null;
    if (!silent) setIsKbLoading(true);
    try {
      const res = await authFetch(`${API_BASE_URL}/api/documents`);
      if (res.status === 401) {
        logout();
        return null;
      }
      if (!res.ok) throw new Error("Failed to fetch docs");
      const data = await res.json();
      const nextCount = Array.isArray(data) ? data.length : 0;
      setDocumentCount(nextCount);
      return nextCount;
    } catch (err) {
      console.error("Failed to check document count:", err);
      return null;
    } finally {
      if (!silent) setIsKbLoading(false);
    }
  };

  useEffect(() => { if (authUser) checkDocumentCount(); }, [authUser]);

  useEffect(() => {
    if (!authUser) return;
    const id = setInterval(() => { checkDocumentCount(true); }, 12000);
    return () => clearInterval(id);
  }, [authUser]);

  const handleModalClose = () => {
    setIsModalOpen(false);
    checkDocumentCount();
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const patchConv = (id: string, updater: (c: Conversation) => Conversation) =>
    setConversations((prev) => prev.map((c) => (c.id === id ? updater(c) : c)));

  const pushMessage = (convId: string, msg: Message) =>
    patchConv(convId, (c) => ({ ...c, messages: [...c.messages, msg] }));

  const startNewChat = async () => {
    if (!token || isCreatingNewChat || newChatClickLockRef.current) return;
    newChatClickLockRef.current = true;
    setIsCreatingNewChat(true);

    // Don't open another blank chat if the active one is already empty
    if (activeConversation && activeConversation.messages.length === 0) {
      setIsCreatingNewChat(false);
      newChatClickLockRef.current = false;
      return;
    }

    try {
      const conv = await createRemoteConversation();
      if (!conv) return;
      setConversations((prev) => [conv, ...prev]);
      setActiveId(conv.id);
      setMobileView("chat");
    } catch (e) {
      console.error(e);
      showError("Failed to create conversation");
    } finally {
      setIsCreatingNewChat(false);
      newChatClickLockRef.current = false;
    }
  };

  const deleteConversation = async (id: string) => {
    if (!token) return;
    try {
      const res = await authFetch(`${API_BASE_URL}/api/history/conversations/${id}`, {
        method: "DELETE",
      });
      if (res.status === 401) {
        logout();
        return;
      }
      if (!res.ok) {
        throw new Error("Failed to delete conversation");
      }

      setConversations((prev) => {
        const next = prev.filter((c) => c.id !== id);
        if (id === activeIdRef.current) {
          if (next.length === 0) {
            return [];
          }
          setActiveId(next[0].id);
        }
        return next;
      });
    } catch (e) {
      console.error(e);
      showError("Failed to delete conversation");
    }
  };

  const formatRelativeTime = (date: Date) => {
    const diff = Date.now() - date.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  const sendQuery = async (query: string) => {
    if (!query.trim() || isLoading || !token) return;
    let currentId = activeIdRef.current;

    if (!currentId) {
      const created = await createRemoteConversation();
      if (!created) return;
      setConversations((prev) => [created, ...prev]);
      setActiveId(created.id);
      currentId = created.id;
    }

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: query,
      timestamp: new Date(),
    };
    setConversations((prev) =>
      prev.map((c) => {
        if (c.id !== currentId) return c;
        const hasUserMessage = c.messages.some((m) => m.role === "user");
        return {
          ...c,
          title: !hasUserMessage ? query.slice(0, 42) + (query.length > 42 ? "…" : "") : c.title,
          messages: [...c.messages, userMessage],
        };
      })
    );
    setInput("");
    setIsLoading(true);
    try {
      const res = await authFetch(`${API_BASE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, conversation_id: currentId }),
      });
      if (res.status === 401) {
        logout();
        throw new Error("Session expired. Please sign in again.");
      }
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Chat failed: ${res.status}`);
      }
      const data = await res.json();
      if (data.conversation_id && data.conversation_id !== currentId) {
        currentId = data.conversation_id;
        setActiveId(currentId);
      }
      if (data.conversation_title) {
        patchConv(currentId, (c) => ({ ...c, title: data.conversation_title }));
      }
      pushMessage(currentId, {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.answer,
        sources: data.sources,
        timestamp: new Date(),
      });
    } catch (err) {
      console.error(err);
      pushMessage(currentId, {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "Sorry, I encountered an error connecting to my brain.",
        timestamp: new Date(),
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendQuery(input);
  };

  const handleCopy = async (id: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {}
  };

  const submitAuth = async (mode: "login" | "register") => {
    setAuthError(null);
    setAuthLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: authEmail,
          password: authPassword,
          ...(mode === "register" ? { full_name: authFullName } : {}),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `${mode} failed`);
      persistSession(data.access_token, data.user);
      setProfileName(data.user?.full_name || "");
      setProfileBio(data.user?.bio || "");
      setAuthFullName("");
      setAuthEmail("");
      setAuthPassword("");
    } catch (e) {
      setAuthError(e instanceof Error ? e.message : "Authentication failed");
    } finally {
      setAuthLoading(false);
    }
  };

  const guestAuth = async () => {
    setAuthError(null);
    setAuthLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/guest`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Guest login failed");
      persistSession(data.access_token, data.user);
      setProfileName(data.user?.full_name || "");
      setProfileBio(data.user?.bio || "");
    } catch (e) {
      setAuthError(e instanceof Error ? e.message : "Guest login failed");
    } finally {
      setAuthLoading(false);
    }
  };

  const saveProfile = async () => {
    if (!token || !authUser || authUser.is_guest) return;
    setProfileSaving(true);
    setAuthError(null);
    try {
      const res = await authFetch(`${API_BASE_URL}/api/auth/profile`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: profileName, bio: profileBio }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed to update profile");
      const updated = { ...(authUser || {}), ...data } as AuthUser;
      setAuthUser(updated);
      localStorage.setItem("sb_user", JSON.stringify(updated));
      setIsProfileOpen(false);
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to update profile");
    } finally {
      setProfileSaving(false);
    }
  };

  const deleteAccount = async () => {
    if (!token || !authUser) return;
    setDeleteError(null);
    if (authUser.is_guest && deleteConfirmText !== "DELETE") {
      setDeleteError("Type DELETE to confirm account deletion.");
      return;
    }
    if (!authUser.is_guest && !deletePassword.trim()) {
      setDeleteError("Password is required to delete account.");
      return;
    }

    setProfileDeleting(true);
    try {
      const res = await authFetch(`${API_BASE_URL}/api/auth/delete-account`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: deletePassword || undefined }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed to delete account");

      setIsDeleteSheetOpen(false);
      setIsProfileOpen(false);
      setDeletePassword("");
      setDeleteConfirmText("");
      setDeleteError(null);
      logout();
      showError("Account deleted successfully");
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Failed to delete account");
    } finally {
      setProfileDeleting(false);
    }
  };

  if (!authUser) {
    return (
      <div className="min-h-dvh bg-[#08080a] bg-grid flex items-center justify-center p-4">
        <div className="w-full max-w-md rounded-2xl border border-white/[0.08] bg-[#0e0e11]/95 p-6">
          <h2 className="text-xl font-semibold text-white mb-1">Welcome to Second Brain</h2>
          <p className="text-sm text-zinc-500 mb-6">Sign in to access your personal brain, or continue as guest.</p>

          <div className="flex gap-2 mb-4 rounded-xl bg-white/[0.03] p-1 border border-white/[0.06]">
            <button onClick={() => setAuthMode("login")} className={`flex-1 py-2 text-sm rounded-lg ${authMode === "login" ? "bg-blue-600 text-white" : "text-zinc-500"}`}>Login</button>
            <button onClick={() => setAuthMode("register")} className={`flex-1 py-2 text-sm rounded-lg ${authMode === "register" ? "bg-blue-600 text-white" : "text-zinc-500"}`}>Sign up</button>
          </div>

          <div className="space-y-3">
            {authMode === "register" && (
              <input
                value={authFullName}
                onChange={(e) => setAuthFullName(e.target.value)}
                placeholder="Full Name"
                className="w-full rounded-xl bg-white/[0.03] border border-white/[0.08] px-3 py-2.5 text-sm text-white"
              />
            )}
            <input
              value={authEmail}
              onChange={(e) => setAuthEmail(e.target.value)}
              placeholder="Email"
              className="w-full rounded-xl bg-white/[0.03] border border-white/[0.08] px-3 py-2.5 text-sm text-white"
            />
            <input
              type="password"
              value={authPassword}
              onChange={(e) => setAuthPassword(e.target.value)}
              placeholder="Password"
              className="w-full rounded-xl bg-white/[0.03] border border-white/[0.08] px-3 py-2.5 text-sm text-white"
            />
            {authError && <p className="text-xs text-red-400">{authError}</p>}
            <button
              onClick={() => submitAuth(authMode)}
              disabled={authLoading || !authEmail || !authPassword || (authMode === "register" && !authFullName.trim())}
              className="w-full py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-sm"
            >
              {authLoading ? "Please wait..." : authMode === "login" ? "Login" : "Create account"}
            </button>
            <button
              onClick={guestAuth}
              disabled={authLoading}
              className="w-full py-2.5 rounded-xl bg-white/[0.06] hover:bg-white/[0.1] disabled:opacity-40 text-zinc-200 text-sm"
            >
              Continue as Guest
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col lg:flex-row h-dvh lg:h-screen overflow-hidden bg-[#08080a] bg-grid">
      {/* ── LEFT: Chat History ── */}
      <aside
        className={`flex flex-col flex-shrink-0 border-white/[0.05] ${
          mobileView === "history"
            ? "fixed inset-x-0 top-0 bottom-16 z-30 w-full border-r-0"
            : "hidden"
        } lg:static lg:z-auto lg:flex lg:w-60 lg:border-r`}
        style={{ background: "rgba(9,9,11,0.92)", backdropFilter: "blur(24px)" }}
      >
        {/* Logo */}
        <div className="h-14 px-5 border-b border-white/[0.05] flex items-center flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center flex-shrink-0 shadow-lg shadow-blue-900/30">
              <BrainIcon size={15} />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-white leading-tight">Second Brain</h1>
              <p className="text-[11px] text-zinc-600 leading-tight">Agentic Knowledge Hub</p>
            </div>
          </div>
        </div>

        {/* New Chat button */}
        <div className="p-3 border-b border-white/[0.05]">
          <button
            onClick={startNewChat}
              disabled={isCreatingNewChat}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-white/[0.05] hover:bg-white/[0.09] border border-white/[0.07] hover:border-white/[0.12] active:scale-[0.98] transition-all rounded-xl text-zinc-300 font-medium text-sm disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
              {isCreatingNewChat ? "Creating..." : "New Chat"}
          </button>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto custom-scrollbar py-1.5">
          {conversations.length === 0 ? (
            <p className="text-xs text-zinc-700 text-center py-8">No conversations yet</p>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                className={`group flex items-center gap-1 pr-1 transition-colors relative ${
                  conv.id === activeId
                    ? "bg-white/[0.07]"
                    : "hover:bg-white/[0.04]"
                }`}
              >
                {conv.id === activeId && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-blue-500 rounded-r-full" />
                )}
                <button
                  onClick={() => setActiveId(conv.id)}
                  className={`flex-1 text-left px-3 py-2.5 min-w-0 ${
                    conv.id === activeId ? "text-zinc-200" : "text-zinc-500 group-hover:text-zinc-300"
                  }`}
                >
                  <div className="pl-2">
                    <div className="text-[13px] leading-snug truncate font-medium">{conv.title}</div>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className="text-[11px] text-zinc-700 tabular-nums">{formatRelativeTime(conv.createdAt)}</span>
                      {conv.messages.length > 0 && (
                        <span className="text-[11px] text-zinc-800">
                          · {conv.messages.length} msg{conv.messages.length !== 1 ? "s" : ""}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
                {confirmDeleteId === conv.id ? (
                  <div className="flex items-center gap-1 flex-shrink-0 pr-1">
                    <span className="text-[11px] text-zinc-500 whitespace-nowrap">Delete?</span>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteConversation(conv.id); setConfirmDeleteId(null); }}
                      className="text-[11px] px-1.5 py-0.5 rounded bg-red-600/80 hover:bg-red-500 text-white font-medium transition-colors"
                    >Yes</button>
                    <button
                      onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(null); }}
                      className="text-[11px] px-1.5 py-0.5 rounded bg-white/[0.06] hover:bg-white/[0.12] text-zinc-400 font-medium transition-colors"
                    >No</button>
                  </div>
                ) : (
                  <button
                    onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(conv.id); }}
                    className="opacity-0 group-hover:opacity-100 flex-shrink-0 p-1.5 text-zinc-600 hover:text-red-400 transition-all rounded-md hover:bg-white/[0.05]"
                    title="Delete conversation"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </aside>

      {/* ── Main ── */}
      <main className={`${mobileView === "chat" ? "flex" : "hidden"} lg:flex flex-1 flex-col relative overflow-hidden`}>
        {/* Error toast */}
        {error && (
          <div className="fixed top-4 right-4 z-50 max-w-sm bg-red-950/95 border border-red-800/50 rounded-xl px-4 py-3 text-red-200 text-sm shadow-2xl toast-animate">
            <div className="flex items-start gap-2.5">
              <svg className="w-4 h-4 flex-shrink-0 mt-0.5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <span className="flex-1 leading-snug">{error}</span>
              <button onClick={() => setError(null)} className="text-red-500 hover:text-red-300 text-lg leading-none">×</button>
            </div>
          </div>
        )}

        {/* Background glows */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute top-[10%] left-[30%] w-[600px] h-[600px] bg-blue-700/[0.06] rounded-full blur-[130px]" />
          <div className="absolute bottom-[10%] right-[20%] w-[500px] h-[500px] bg-violet-700/[0.055] rounded-full blur-[110px]" />
        </div>

        {/* Header */}
        <header
          className="relative z-10 h-14 flex items-center justify-between px-5 border-b border-white/[0.05] flex-shrink-0"
          style={{ background: "rgba(8,8,10,0.85)", backdropFilter: "blur(24px)" }}
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="lg:hidden flex items-center gap-1">
              <button
                onClick={() => setMobileView("history")}
                className="p-2 text-zinc-500 hover:text-zinc-300 rounded-lg hover:bg-white/[0.05]"
                title="Open chats"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
                </svg>
              </button>
              <button
                onClick={() => setMobileView("kb")}
                className="p-2 text-zinc-500 hover:text-zinc-300 rounded-lg hover:bg-white/[0.05]"
                title="Open knowledge base"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                </svg>
              </button>
            </div>
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-60" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500" />
            </span>
            <span className="text-sm font-medium text-zinc-300 truncate">Agentic RAG Engine</span>
            <span className="hidden sm:inline-flex text-[10px] px-2 py-0.5 rounded-full bg-white/[0.05] text-zinc-600 font-medium border border-white/[0.04]">
              Gemini 2.5
            </span>
          </div>
          <div className="flex items-center gap-1">
            <span className="hidden md:inline-flex text-[10px] px-2 py-1 rounded-full bg-white/[0.08] text-zinc-300 border border-white/[0.12]">
              {authUser.is_guest ? "Guest" : (authUser.full_name || authUser.email)}
            </span>
            {!authUser.is_guest && (
              <button
                onClick={() => setIsProfileOpen(true)}
                className="p-2 text-zinc-500 hover:text-zinc-200 transition-colors rounded-lg hover:bg-white/[0.08]"
                title="Profile"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
                </svg>
              </button>
            )}
            <button
              onClick={logout}
              className="p-2 text-zinc-500 hover:text-zinc-200 transition-colors rounded-lg hover:bg-white/[0.08]"
              title="Logout"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
            <button
              onClick={() => setIsAboutOpen(true)}
              className="p-2 text-zinc-500 hover:text-zinc-200 transition-colors rounded-lg hover:bg-white/[0.08]"
              title="About Second Brain"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" />
              </svg>
            </button>
          </div>
        </header>

        {/* ── Chat history ── */}
        <div className="flex-1 overflow-y-auto custom-scrollbar px-3 sm:px-4 md:px-8 py-5 md:py-8 pb-44 md:pb-36 relative z-10">
          {messages.length === 0 ? (
            /* Empty state */
            <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-600/25 to-violet-600/25 border border-white/[0.07] flex items-center justify-center mb-5 shadow-xl shadow-blue-900/10">
                <BrainIcon size={22} />
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">Ask your Second Brain</h3>
              <p className="text-sm text-zinc-600 max-w-xs mb-8 leading-relaxed">
                Your notes are semantically indexed.<br />Ask anything in plain language.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
                {SUGGESTED_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => sendQuery(prompt)}
                    disabled={isLoading}
                    className="text-left px-4 py-3 rounded-xl border border-white/[0.06] bg-white/[0.025] hover:bg-white/[0.055] hover:border-white/[0.12] transition-all text-sm text-zinc-500 hover:text-zinc-200 group disabled:opacity-40"
                  >
                    <span className="text-blue-600 mr-2 group-hover:text-blue-400 transition-colors">→</span>
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-5">
              {messages.map((msg) => (
                <div key={msg.id} className={`flex gap-3 msg-animate ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
                  {/* Avatar */}
                  <div className={`w-7 h-7 rounded-lg flex-shrink-0 flex items-center justify-center mt-0.5 ${
                    msg.role === "user"
                      ? "bg-blue-600 shadow-md shadow-blue-900/30"
                      : "bg-gradient-to-br from-violet-600 to-purple-700 shadow-md shadow-violet-900/30"
                  }`}>
                    {msg.role === "user" ? (
                      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
                      </svg>
                    ) : (
                      <BrainIcon size={13} />
                    )}
                  </div>

                  {/* Bubble + meta row */}
                  <div className={`flex flex-col gap-1.5 min-w-0 max-w-[82%] ${msg.role === "user" ? "items-end" : "items-start"}`}>
                    <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed break-words ${
                      msg.role === "user"
                        ? "bg-blue-600 text-white rounded-tr-sm shadow-md shadow-blue-900/20"
                        : "bg-white/[0.045] border border-white/[0.07] text-zinc-200 rounded-tl-sm"
                    }`}>
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                    </div>

                    {/* Sources + copy + timestamp */}
                    <div className={`flex flex-wrap items-center gap-1.5 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
                      {msg.sources && msg.sources.length > 0 && msg.sources.map((src, i) => (
                        <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 bg-white/[0.04] border border-white/[0.06] rounded-md text-[11px] text-zinc-600">
                          <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                          {typeof src.score === "number" ? src.score.toFixed(2) : "N/A"}
                        </span>
                      ))}
                      {msg.role === "assistant" && (
                        <button
                          onClick={() => handleCopy(msg.id, msg.content)}
                          className={`inline-flex items-center gap-1 px-2 py-0.5 text-[11px] rounded-md transition-colors ${
                            copiedId === msg.id ? "text-emerald-400" : "text-zinc-700 hover:text-zinc-400 hover:bg-white/[0.04]"
                          }`}
                        >
                          {copiedId === msg.id ? (
                            <><svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg> Copied</>
                          ) : (
                            <><svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg> Copy</>
                          )}
                        </button>
                      )}
                      <span className="text-[10px] text-zinc-800 tabular-nums">
                        {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </div>
                  </div>
                </div>
              ))}

              {/* Typing indicator */}
              {isLoading && (
                <div className="flex gap-3 msg-animate">
                  <div className="w-7 h-7 rounded-lg flex-shrink-0 flex items-center justify-center mt-0.5 bg-gradient-to-br from-violet-600 to-purple-700">
                    <BrainIcon size={13} />
                  </div>
                  <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-white/[0.045] border border-white/[0.07] flex items-center gap-2">
                    <span className="text-xs text-zinc-600">Searching memories</span>
                    <span className="w-1.5 h-1.5 bg-zinc-600 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="w-1.5 h-1.5 bg-zinc-600 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                    <span className="w-1.5 h-1.5 bg-zinc-600 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* ── Input bar ── */}
        <div className="absolute bottom-0 left-0 right-0 z-20 px-3 sm:px-4 md:px-8 pb-20 md:pb-6 pt-10 md:pt-16 bg-gradient-to-t from-[#08080a] via-[#08080a]/90 to-transparent">
          <form onSubmit={handleSubmit} className="max-w-3xl mx-auto flex items-end gap-2">

            {/* File upload */}
            <div>
              <input
                type="file"
                id="file-upload"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  const MAX_FILE_SIZE = 50 * 1024 * 1024;
                  if (file.size > MAX_FILE_SIZE) {
                    showError(`File exceeds 50MB limit (${(file.size / 1024 / 1024).toFixed(1)} MB)`);
                    e.target.value = "";
                    return;
                  }
                  const formData = new FormData();
                  formData.append("file", file);
                  const currentUploadId = activeIdRef.current;
                  pushMessage(currentUploadId, { id: crypto.randomUUID(), role: "assistant", content: `Ingesting ${file.name}…`, timestamp: new Date() });
                  setIsLoading(true);
                  try {
                    const res = await authFetch(`${API_BASE_URL}/api/ingest/upload`, { method: "POST", body: formData });
                    if (res.status === 401) {
                      logout();
                      throw new Error("Session expired. Please sign in again.");
                    }
                    if (res.ok) {
                      pushMessage(currentUploadId, {
                        id: crypto.randomUUID(),
                        role: "assistant",
                        content: `✓ ${file.name} upload accepted. Indexing is running in the background.`,
                        timestamp: new Date(),
                      });

                      // Poll count while background ingestion is expected to complete.
                      setIsKbSyncing(true);
                      const baseline = documentCount;
                      for (let i = 0; i < 12; i++) {
                        await new Promise((resolve) => setTimeout(resolve, 1500));
                        const next = await checkDocumentCount(true);
                        if (typeof next === "number" && next > baseline) {
                          break;
                        }
                      }
                      setIsKbSyncing(false);
                    } else {
                      const d = await res.json().catch(() => ({}));
                      throw new Error(d.detail || "Upload failed");
                    }
                  } catch (err) {
                    const msg = err instanceof Error ? err.message : "Upload failed";
                    showError(msg);
                    pushMessage(currentUploadId, { id: crypto.randomUUID(), role: "assistant", content: `Failed to upload ${file.name}.`, timestamp: new Date() });
                    setIsKbSyncing(false);
                  } finally {
                    setIsLoading(false);
                    e.target.value = "";
                  }
                }}
              />
              <label
                htmlFor="file-upload"
                className="cursor-pointer flex flex-col items-center justify-center w-[52px] h-[52px] border border-white/[0.07] bg-white/[0.03] hover:bg-white/[0.07] hover:border-white/[0.14] rounded-xl transition-all text-zinc-600 hover:text-zinc-300 gap-0.5 select-none"
                title="Upload document (max 50MB)"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                <span className="text-[9px] font-semibold">50MB</span>
              </label>
            </div>

            {/* Text input */}
            <div className="flex-1 relative">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-r from-blue-600/25 to-violet-600/25 opacity-0 focus-within:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative flex items-center bg-white/[0.04] border border-white/[0.08] rounded-2xl focus-within:border-white/[0.16] transition-colors shadow-xl">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask your second brain…"
                  className="flex-1 bg-transparent px-4 py-3.5 text-sm outline-none text-zinc-100 placeholder-zinc-700"
                  maxLength={5000}
                  disabled={isLoading}
                />
                {input.length > 0 && (
                  <span className={`text-[11px] pr-2 tabular-nums flex-shrink-0 ${
                    input.length > 4500 ? "text-red-400" : input.length > 3500 ? "text-yellow-500" : "text-zinc-700"
                  }`}>
                    {input.length}/5k
                  </span>
                )}
                <button
                  type="submit"
                  disabled={!input.trim() || isLoading}
                  className="m-1.5 p-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-30 disabled:hover:bg-blue-600 rounded-xl transition-all active:scale-95 text-white flex-shrink-0 shadow-md shadow-blue-900/30"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                </button>
              </div>
            </div>
          </form>
        </div>
      </main>

      {/* ── RIGHT: Memory Banks + Brain Management ── */}
      <aside
        className={`flex flex-col flex-shrink-0 border-white/[0.05] ${
          mobileView === "kb"
            ? "fixed inset-x-0 top-0 bottom-16 z-30 w-full border-l-0"
            : "hidden"
        } lg:static lg:z-auto lg:flex lg:w-56 lg:border-l`}
        style={{ background: "rgba(9,9,11,0.92)", backdropFilter: "blur(24px)" }}
      >
        <div className="h-14 px-4 border-b border-white/[0.05] flex items-center flex-shrink-0">
          <p className="text-xs font-semibold text-zinc-600 uppercase tracking-widest">Knowledge Base</p>
        </div>

        <div className="px-3 py-4 flex-1 space-y-6 overflow-y-auto custom-scrollbar">
          <div>
            <p className="text-[10px] font-semibold text-zinc-700 uppercase tracking-widest px-2 mb-1.5">Memory Banks</p>
            <div className={`flex items-center justify-between px-3 py-2.5 rounded-xl transition-colors ${documentCount > 0 ? "bg-white/[0.06]" : "bg-transparent"}`}>
              <div className="flex items-center gap-2.5 min-w-0">
                {isKbLoading || isKbSyncing ? (
                  <span className="relative flex h-2 w-2 flex-shrink-0">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-60" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
                  </span>
                ) : documentCount > 0 ? (
                  <span className="relative flex h-2 w-2 flex-shrink-0">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                  </span>
                ) : (
                  <span className="w-2 h-2 rounded-full bg-zinc-800 flex-shrink-0" />
                )}
                <span className={`text-sm truncate ${documentCount > 0 ? "text-zinc-200" : "text-zinc-600"}`}>{isKbLoading ? "Loading Knowledge Base..." : isKbSyncing ? "Syncing Knowledge Base..." : "Qdrant Vector DB"}</span>
              </div>
              {(documentCount > 0 || isKbLoading || isKbSyncing) && (
                <span className="text-[11px] font-semibold bg-emerald-500/15 text-emerald-400 px-2 py-0.5 rounded-full flex-shrink-0 tabular-nums">
                  {isKbLoading ? "..." : documentCount}
                </span>
              )}
            </div>
          </div>

          <div>
            <p className="text-[10px] font-semibold text-zinc-700 uppercase tracking-widest px-2 mb-1.5">Coming Soon</p>
            <div className="space-y-0.5 opacity-35 pointer-events-none select-none">
              {["Notion Workspace", "Google Workspace"].map((name) => (
                <div key={name} className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-zinc-600">
                  <span className="w-2 h-2 rounded-full bg-zinc-800 flex-shrink-0" />
                  <span className="text-sm">{name}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="p-3 border-t border-white/[0.05]">
          <button
            onClick={() => setIsModalOpen(true)}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 active:scale-[0.98] transition-all rounded-xl text-white font-medium text-sm shadow-lg shadow-blue-900/25"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
            </svg>
            Brain Management
          </button>
        </div>
      </aside>

      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-40 border-t border-white/[0.08] bg-[#09090b]/95 backdrop-blur-xl">
        <div className="grid grid-cols-3 gap-1 p-2">
          <button
            onClick={() => setMobileView("history")}
            className={`px-3 py-2 rounded-xl text-xs font-medium transition-colors ${mobileView === "history" ? "bg-white/[0.1] text-zinc-100" : "text-zinc-500"}`}
          >
            Chats
          </button>
          <button
            onClick={() => setMobileView("chat")}
            className={`px-3 py-2 rounded-xl text-xs font-medium transition-colors ${mobileView === "chat" ? "bg-blue-600 text-white" : "text-zinc-500"}`}
          >
            Chat
          </button>
          <button
            onClick={() => setMobileView("kb")}
            className={`px-3 py-2 rounded-xl text-xs font-medium transition-colors ${mobileView === "kb" ? "bg-white/[0.1] text-zinc-100" : "text-zinc-500"}`}
          >
            Knowledge
          </button>
        </div>
      </nav>

      <KnowledgeModal isOpen={isModalOpen} onClose={handleModalClose} />
      <AboutModal isOpen={isAboutOpen} onClose={() => setIsAboutOpen(false)} />

      {isProfileOpen && authUser && !authUser.is_guest && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)" }}>
          <div className="w-full max-w-md rounded-2xl border border-white/[0.08] bg-[#0e0e11]/95 p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-white">Profile</h3>
              <button onClick={() => setIsProfileOpen(false)} className="text-zinc-600 hover:text-zinc-300">×</button>
            </div>

            <div className="space-y-3">
              <div>
                <p className="text-xs text-zinc-600 mb-1">Email</p>
                <p className="text-sm text-zinc-300 break-all">{authUser.email}</p>
              </div>
              <div>
                <p className="text-xs text-zinc-600 mb-1">Account Type</p>
                <p className="text-sm text-zinc-300">Registered</p>
              </div>

              <div>
                <p className="text-xs text-zinc-600 mb-1">Full Name</p>
                <input
                  value={profileName}
                  onChange={(e) => setProfileName(e.target.value)}
                  disabled={false}
                  className="w-full rounded-xl bg-white/[0.03] border border-white/[0.08] px-3 py-2.5 text-sm text-white disabled:opacity-50"
                />
              </div>

              <div>
                <p className="text-xs text-zinc-600 mb-1">Bio</p>
                <textarea
                  value={profileBio}
                  onChange={(e) => setProfileBio(e.target.value)}
                  disabled={false}
                  rows={3}
                  className="w-full rounded-xl bg-white/[0.03] border border-white/[0.08] px-3 py-2.5 text-sm text-white disabled:opacity-50"
                />
              </div>

              <button
                onClick={saveProfile}
                disabled={profileSaving}
                className="w-full py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm"
              >
                {profileSaving ? "Saving..." : "Save Profile"}
              </button>
              <button
                onClick={() => setIsDeleteSheetOpen(true)}
                disabled={profileDeleting}
                className="w-full py-2.5 rounded-xl bg-red-600/90 hover:bg-red-500 disabled:opacity-50 text-white text-sm"
              >
                {profileDeleting ? "Deleting..." : "Delete Account"}
              </button>
            </div>
          </div>
        </div>
      )}

      {isDeleteSheetOpen && authUser && !authUser.is_guest && (
        <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center p-0 sm:p-4" style={{ background: "rgba(0,0,0,0.75)", backdropFilter: "blur(8px)" }}>
          <div className="w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl border border-white/[0.08] bg-[#111114] p-5 sm:p-6 shadow-2xl">
            <div className="w-10 h-1 rounded-full bg-white/[0.18] mx-auto mb-4 sm:hidden" />
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-semibold text-white">Delete Account</h3>
              <button
                onClick={() => {
                  setIsDeleteSheetOpen(false);
                  setDeletePassword("");
                  setDeleteConfirmText("");
                  setDeleteError(null);
                }}
                className="text-zinc-600 hover:text-zinc-300"
              >
                ×
              </button>
            </div>

            <p className="text-sm text-zinc-400 mb-4">
              This permanently deletes your account and private brain data. This action cannot be undone.
            </p>

            {!authUser.is_guest && (
              <div className="mb-3">
                <p className="text-xs text-zinc-600 mb-1">Confirm password</p>
                <input
                  type="password"
                  value={deletePassword}
                  onChange={(e) => setDeletePassword(e.target.value)}
                  className="w-full rounded-xl bg-white/[0.03] border border-white/[0.08] px-3 py-2.5 text-sm text-white"
                  placeholder="Enter your password"
                />
              </div>
            )}

            {authUser.is_guest && (
              <div className="mb-4">
                <p className="text-xs text-zinc-600 mb-1">Type DELETE to confirm</p>
                <input
                  value={deleteConfirmText}
                  onChange={(e) => setDeleteConfirmText(e.target.value)}
                  className="w-full rounded-xl bg-white/[0.03] border border-white/[0.08] px-3 py-2.5 text-sm text-white"
                  placeholder="DELETE"
                />
              </div>
            )}

            {deleteError && (
              <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                {deleteError}
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={() => {
                  setIsDeleteSheetOpen(false);
                  setDeletePassword("");
                  setDeleteConfirmText("");
                  setDeleteError(null);
                }}
                className="flex-1 py-2.5 rounded-xl bg-white/[0.06] hover:bg-white/[0.1] text-zinc-300 text-sm"
              >
                Cancel
              </button>
              <button
                onClick={deleteAccount}
                disabled={
                  profileDeleting ||
                  (!authUser.is_guest && !deletePassword.trim()) ||
                  (authUser.is_guest && deleteConfirmText !== "DELETE")
                }
                className="flex-1 py-2.5 rounded-xl bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white text-sm"
              >
                {profileDeleting ? "Deleting..." : "Delete Forever"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
