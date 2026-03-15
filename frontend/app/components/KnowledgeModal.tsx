"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
const DRAFT_KEY = "second-brain-direct-note-draft-v1";

type DocumentListItem = {
  id: string;
  source: string;
  title: string;
  content_snippet: string;
};

type EditorMode = "write" | "split" | "preview";

export default function KnowledgeModal({ isOpen, onClose }: { isOpen: boolean, onClose: () => void }) {
  const [activeTab, setActiveTab] = useState("list");
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newText, setNewText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editorMode, setEditorMode] = useState<EditorMode>("write");
  const [saveStatus, setSaveStatus] = useState("Draft not saved yet");
  const [error, setError] = useState<string | null>(null);
  const textAreaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isOpen && activeTab === "list") {
      fetchDocs();
    }
  }, [isOpen, activeTab]);

  const fetchDocs = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/documents`);
      if (!res.ok) {
        throw new Error(`Failed to fetch documents: ${res.status}`);
      }
      const data = await res.json();
      setDocuments(data);
      setError(null);
    } catch (e) {
      console.error("Failed to fetch documents", e);
      const errorMsg = e instanceof Error ? e.message : "Failed to fetch documents";
      setError(errorMsg);
    }
  };

  const handleDelete = async (id: string) => {
    setConfirmDeleteId(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/documents/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to delete document: ${res.status}`);
      }
      setError(null);
      fetchDocs();
    } catch (e) {
      console.error("Failed to delete", e);
      const errorMsg = e instanceof Error ? e.message : "Failed to delete document";
      setError(errorMsg);
    }
  };

  const handleIngest = async () => {
    if (!newTitle || !newText) return;
    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/ingest/text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle, text: newText })
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to ingest note: ${res.status}`);
      }
      setNewTitle("");
      setNewText("");
      localStorage.removeItem(DRAFT_KEY);
      setSaveStatus("Draft cleared after commit");
      setError(null);
      
      // Wait for background task to complete before switching tabs and fetching
      await new Promise((resolve) => window.setTimeout(resolve, 800));
      
      await fetchDocs();
      setActiveTab("list");
    } catch (e) {
      console.error("Failed to ingest", e);
      const errorMsg = e instanceof Error ? e.message : "Failed to ingest note";
      setError(errorMsg);
    } finally {
      setIsSubmitting(false);
    }
  };

  useEffect(() => {
    if (!isOpen || activeTab !== "add") return;

    const rawDraft = localStorage.getItem(DRAFT_KEY);
    if (!rawDraft) return;

    try {
      const parsed = JSON.parse(rawDraft) as { title?: string; text?: string; savedAt?: string };
      if (parsed.title) setNewTitle(parsed.title);
      if (parsed.text) setNewText(parsed.text);
      if (parsed.savedAt) {
        setSaveStatus(`Restored draft from ${new Date(parsed.savedAt).toLocaleTimeString()}`);
      }
    } catch {
      setSaveStatus("Draft restore failed");
    }
  }, [isOpen, activeTab]);

  useEffect(() => {
    if (!isOpen || activeTab !== "add") return;

    setSaveStatus("Saving draft...");
    const timer = window.setTimeout(() => {
      const savedAt = new Date().toISOString();
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ title: newTitle, text: newText, savedAt }));
      setSaveStatus(`Saved at ${new Date(savedAt).toLocaleTimeString()}`);
    }, 500);

    return () => window.clearTimeout(timer);
  }, [newTitle, newText, isOpen, activeTab]);

  const textStats = useMemo(() => {
    const words = newText.trim() ? newText.trim().split(/\s+/).length : 0;
    const characters = newText.length;
    const lines = newText ? newText.split(/\r?\n/).length : 0;
    return { words, characters, lines };
  }, [newText]);

  const insertAroundSelection = (before: string, after = before, placeholder = "text") => {
    const textarea = textAreaRef.current;
    if (!textarea) {
      setNewText((prev) => `${prev}${before}${placeholder}${after}`);
      return;
    }

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = newText.slice(start, end) || placeholder;
    const updated = `${newText.slice(0, start)}${before}${selectedText}${after}${newText.slice(end)}`;

    setNewText(updated);
    requestAnimationFrame(() => {
      textarea.focus();
      const cursorEnd = start + before.length + selectedText.length + after.length;
      textarea.setSelectionRange(cursorEnd, cursorEnd);
    });
  };

  const insertLineTemplate = (prefix: string) => {
    setNewText((prev) => `${prev}${prev.endsWith("\n") || prev.length === 0 ? "" : "\n"}${prefix}`);
    requestAnimationFrame(() => textAreaRef.current?.focus());
  };

  const clearDraft = () => {
    const ok = window.confirm("Clear this note and remove saved draft?");
    if (!ok) return;
    setNewTitle("");
    setNewText("");
    localStorage.removeItem(DRAFT_KEY);
    setSaveStatus("Draft cleared");
  };

  const downloadDraft = () => {
    const title = (newTitle || "untitled-note").trim().replace(/\s+/g, "-").toLowerCase();
    const blob = new Blob([`# ${newTitle || "Untitled"}\n\n${newText}`], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${title}.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (!isOpen) return null;

  const filteredDocs = documents.filter(d =>
    d.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    d.content_snippet.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)"}}>
      <div className="bg-[#0c0c0e] border border-white/[0.07] rounded-2xl shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[85vh]">
        
        {/* Error banner */}
        {error && (
          <div className="bg-red-950/80 border-b border-red-900/50 px-4 py-2.5 text-red-300 text-xs flex items-start gap-2">
            <svg className="w-4 h-4 flex-shrink-0 mt-0.5 text-red-400" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" /></svg>
            <span className="flex-1 leading-snug">{error}</span>
            <button onClick={() => setError(null)} className="text-red-500 hover:text-red-300 text-base leading-none">×</button>
          </div>
        )}

        {/* Header */}
        <div className="px-5 py-4 border-b border-white/[0.06] flex justify-between items-center" style={{background: "rgba(14,14,16,0.9)"}}>
          <h2 className="text-base font-semibold text-white">Brain Management</h2>
          <button onClick={onClose} className="p-1.5 text-zinc-600 hover:text-zinc-300 transition-colors rounded-lg hover:bg-white/[0.06]">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-white/[0.06]" style={{background: "rgba(14,14,16,0.9)"}}>
          <button
            className={`flex-1 py-3 text-xs font-semibold uppercase tracking-wider transition-colors ${activeTab === 'list' ? 'text-blue-400 border-b-2 border-blue-500' : 'text-zinc-600 hover:text-zinc-400'}`}
            onClick={() => setActiveTab('list')}
          >
            Manage Memory
          </button>
          <button
            className={`flex-1 py-3 text-xs font-semibold uppercase tracking-wider transition-colors ${activeTab === 'add' ? 'text-blue-400 border-b-2 border-blue-500' : 'text-zinc-600 hover:text-zinc-400'}`}
            onClick={() => setActiveTab('add')}
          >
            Add Note
          </button>
        </div>

        {/* Content Area */}
        <div className="p-6 overflow-y-auto flex-1">
          {activeTab === 'list' && (
            <div className="space-y-3">
              {/* Search */}
              <div className="relative">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                <input
                  type="text"
                  placeholder="Search by title or content…"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  className="w-full bg-white/[0.03] border border-white/[0.07] rounded-xl pl-8 pr-4 py-2.5 text-sm text-zinc-300 placeholder-zinc-700 outline-none focus:border-white/[0.15] transition-colors"
                />
              </div>

              {filteredDocs.length === 0 ? (
                <div className="text-center py-12 text-zinc-700">
                  {documents.length === 0 ? "Your second brain is empty. Add some notes!" : `No results for "${searchQuery}"`}
                </div>
              ) : (
                filteredDocs.map(doc => (
                  <div key={doc.id} className="bg-white/[0.03] border border-white/[0.06] hover:border-white/[0.1] p-4 rounded-xl transition-colors group">
                    {confirmDeleteId === doc.id ? (
                      /* Inline delete confirmation */
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm text-zinc-400">Delete <span className="text-white font-medium">{doc.title}</span>?</p>
                        <div className="flex gap-2 flex-shrink-0">
                          <button
                            onClick={() => setConfirmDeleteId(null)}
                            className="px-3 py-1.5 text-xs rounded-lg bg-white/[0.06] text-zinc-300 hover:bg-white/[0.1] transition-colors"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => handleDelete(doc.id)}
                            className="px-3 py-1.5 text-xs rounded-lg bg-red-600/80 hover:bg-red-600 text-white transition-colors"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex justify-between items-start gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="text-sm font-medium text-zinc-100 truncate">{doc.title}</h3>
                            <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-white/[0.06] text-zinc-600 uppercase tracking-wider flex-shrink-0">{doc.source}</span>
                          </div>
                          <p className="text-xs text-zinc-600 line-clamp-2 leading-relaxed">{doc.content_snippet}</p>
                        </div>
                        <button
                          onClick={() => setConfirmDeleteId(doc.id)}
                          className="text-zinc-800 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all p-1.5 hover:bg-red-500/10 rounded-lg flex-shrink-0"
                          title="Delete"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                        </button>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'add' && (
            <div className="space-y-4 flex flex-col h-full">
              <input
                type="text"
                placeholder="Note Title (e.g., 'Docker Troubleshooting')"
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-3 text-sm text-white outline-none focus:border-blue-500/50 transition-colors placeholder-zinc-700"
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
              />

              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => insertAroundSelection("**")}
                  className="px-3 py-1.5 rounded-lg bg-[#18181b] border border-[#27272a] text-xs text-[#e4e4e7] hover:border-blue-500"
                  type="button"
                >
                  Bold
                </button>
                <button
                  onClick={() => insertAroundSelection("*")}
                  className="px-3 py-1.5 rounded-lg bg-[#18181b] border border-[#27272a] text-xs text-[#e4e4e7] hover:border-blue-500"
                  type="button"
                >
                  Italic
                </button>
                <button
                  onClick={() => insertLineTemplate("## Heading")}
                  className="px-3 py-1.5 rounded-lg bg-[#18181b] border border-[#27272a] text-xs text-[#e4e4e7] hover:border-blue-500"
                  type="button"
                >
                  Heading
                </button>
                <button
                  onClick={() => insertLineTemplate("- ")}
                  className="px-3 py-1.5 rounded-lg bg-[#18181b] border border-[#27272a] text-xs text-[#e4e4e7] hover:border-blue-500"
                  type="button"
                >
                  Bullet
                </button>
                <button
                  onClick={() => insertLineTemplate("[ ] ")}
                  className="px-3 py-1.5 rounded-lg bg-[#18181b] border border-[#27272a] text-xs text-[#e4e4e7] hover:border-blue-500"
                  type="button"
                >
                  Checklist
                </button>
                <button
                  onClick={() => insertAroundSelection("`")}
                  className="px-3 py-1.5 rounded-lg bg-[#18181b] border border-[#27272a] text-xs text-[#e4e4e7] hover:border-blue-500"
                  type="button"
                >
                  Inline Code
                </button>
                <button
                  onClick={() => insertLineTemplate(`> ${new Date().toLocaleDateString()} note`)}
                  className="px-3 py-1.5 rounded-lg bg-[#18181b] border border-[#27272a] text-xs text-[#e4e4e7] hover:border-blue-500"
                  type="button"
                >
                  Timestamp
                </button>

                <div className="ml-auto flex items-center gap-1 bg-[#18181b] rounded-lg border border-[#27272a] p-1">
                  <button
                    type="button"
                    onClick={() => setEditorMode("write")}
                    className={`px-2.5 py-1 text-xs rounded-md ${editorMode === "write" ? "bg-blue-600 text-white" : "text-[#a1a1aa]"}`}
                  >
                    Write
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditorMode("split")}
                    className={`px-2.5 py-1 text-xs rounded-md ${editorMode === "split" ? "bg-blue-600 text-white" : "text-[#a1a1aa]"}`}
                  >
                    Split
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditorMode("preview")}
                    className={`px-2.5 py-1 text-xs rounded-md ${editorMode === "preview" ? "bg-blue-600 text-white" : "text-[#a1a1aa]"}`}
                  >
                    Preview
                  </button>
                </div>
              </div>

              <div className={`grid gap-3 flex-1 min-h-[280px] ${editorMode === "split" ? "md:grid-cols-2" : "grid-cols-1"}`}>
                {(editorMode === "write" || editorMode === "split") && (
                  <textarea
                    ref={textAreaRef}
                    placeholder="Type your notes here… Use Cmd/Ctrl+S to commit quickly."
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-3 text-sm text-white outline-none focus:border-blue-500/50 transition-colors flex-1 min-h-[280px] resize-none placeholder-zinc-700"
                    value={newText}
                    onChange={(e) => setNewText(e.target.value)}
                    onKeyDown={(e) => {
                      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
                        e.preventDefault();
                        void handleIngest();
                      }
                    }}
                    spellCheck
                  />
                )}

                {(editorMode === "preview" || editorMode === "split") && (
                  <div className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-3 text-zinc-300 overflow-auto min-h-[280px]">
                    <div className="text-xs text-[#a1a1aa] uppercase tracking-wide mb-2">Live Preview</div>
                    <pre className="whitespace-pre-wrap break-words font-sans leading-relaxed">
                      {newText || "Nothing to preview yet. Start writing in the editor."}
                    </pre>
                  </div>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-3 text-xs text-[#a1a1aa]">
                <span>{textStats.words} words</span>
                <span className={textStats.characters > 9_000_000 ? "text-red-400" : textStats.characters > 7_000_000 ? "text-yellow-400" : ""}>
                  {textStats.characters.toLocaleString()} / 10M chars
                </span>
                <span>{textStats.lines} lines</span>
                <span className="ml-auto">{saveStatus}</span>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={downloadDraft}
                  disabled={!newText.trim() && !newTitle.trim()}
                  className="px-4 py-2 rounded-xl border border-[#27272a] bg-[#18181b] text-[#e4e4e7] hover:border-blue-500 disabled:opacity-50"
                >
                  Export .txt
                </button>
                <button
                  type="button"
                  onClick={clearDraft}
                  disabled={!newText.trim() && !newTitle.trim()}
                  className="px-4 py-2 rounded-xl border border-[#3f3f46] bg-transparent text-[#a1a1aa] hover:text-white hover:border-red-500 disabled:opacity-50"
                >
                  Clear
                </button>
              </div>

              <button 
                onClick={handleIngest}
                disabled={isSubmitting || !newTitle || !newText}
                className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white font-medium py-3 rounded-xl transition-all text-sm active:scale-[0.99]"
              >
                {isSubmitting ? "Ingesting into Vector DB…" : "Commit to Memory"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
