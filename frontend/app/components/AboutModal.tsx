"use client";

export default function AboutModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-[#09090b] border border-[#27272a] rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 p-6 border-b border-[#27272a] flex justify-between items-center bg-[#18181b]">
          <h2 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-500">
            About Second Brain
          </h2>
          <button onClick={onClose} className="text-[#a1a1aa] hover:text-white transition">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* What is it */}
          <section>
            <h3 className="text-lg font-semibold text-white mb-3">What is Second Brain?</h3>
            <p className="text-[#a1a1aa] leading-relaxed">
              Second Brain is an <strong className="text-white">Agentic RAG (Retrieval-Augmented Generation) Engine</strong> that turns your notes and documents into a searchable knowledge system. You upload content, it is chunked and embedded, and your questions are answered from retrieved context with source-backed responses.
            </p>
          </section>

          {/* How it works */}
          <section>
            <h3 className="text-lg font-semibold text-white mb-3">How It Works</h3>
            <div className="space-y-4">
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/50 flex items-center justify-center text-blue-400 font-semibold">1</div>
                <div>
                  <h4 className="text-white font-medium">Ingest</h4>
                  <p className="text-sm text-[#a1a1aa]">Upload PDF/TXT/MD/CSV files or commit notes directly in Brain Management.</p>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-purple-600/20 border border-purple-500/50 flex items-center justify-center text-purple-400 font-semibold">2</div>
                <div>
                  <h4 className="text-white font-medium">Chunk & Embed</h4>
                  <p className="text-sm text-[#a1a1aa]">Content is split into configurable chunks (default 500 words with 50 overlap) and embedded with all-MiniLM-L6-v2 (384-dim).</p>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-green-600/20 border border-green-500/50 flex items-center justify-center text-green-400 font-semibold">3</div>
                <div>
                  <h4 className="text-white font-medium">Store</h4>
                  <p className="text-sm text-[#a1a1aa]">Document metadata is stored in <strong className="text-white">Supabase PostgreSQL</strong>; vector chunks are stored in <strong className="text-white">Qdrant Cloud</strong> with a payload index for reliable delete/filter operations.</p>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-cyan-600/20 border border-cyan-500/50 flex items-center justify-center text-cyan-400 font-semibold">4</div>
                <div>
                  <h4 className="text-white font-medium">Retrieve & Answer</h4>
                  <p className="text-sm text-[#a1a1aa]">On each query, top-k chunks are retrieved from Qdrant and passed to Gemini 2.5 for grounded answers.</p>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-orange-600/20 border border-orange-500/50 flex items-center justify-center text-orange-400 font-semibold">5</div>
                <div>
                  <h4 className="text-white font-medium">Background Sync UX</h4>
                  <p className="text-sm text-[#a1a1aa]">Uploads are processed in the background; the sidebar now shows loading/syncing states until memory-bank counts refresh.</p>
                </div>
              </div>
            </div>
          </section>

          {/* Tech Stack */}
          <section>
            <h3 className="text-lg font-semibold text-white mb-3">Architecture</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-[#18181b] border border-[#27272a] rounded-lg p-3">
                <p className="text-xs text-[#a1a1aa] uppercase tracking-wide font-medium">Frontend</p>
                <p className="text-white font-medium mt-1">Next.js + React</p>
              </div>
              <div className="bg-[#18181b] border border-[#27272a] rounded-lg p-3">
                <p className="text-xs text-[#a1a1aa] uppercase tracking-wide font-medium">Backend</p>
                <p className="text-white font-medium mt-1">FastAPI (Python)</p>
              </div>
              <div className="bg-[#18181b] border border-[#27272a] rounded-lg p-3">
                <p className="text-xs text-[#a1a1aa] uppercase tracking-wide font-medium">Vectors</p>
                <p className="text-white font-medium mt-1">Qdrant Cloud</p>
              </div>
              <div className="bg-[#18181b] border border-[#27272a] rounded-lg p-3">
                <p className="text-xs text-[#a1a1aa] uppercase tracking-wide font-medium">Metadata</p>
                <p className="text-white font-medium mt-1">Supabase PostgreSQL</p>
              </div>
              <div className="bg-[#18181b] border border-[#27272a] rounded-lg p-3">
                <p className="text-xs text-[#a1a1aa] uppercase tracking-wide font-medium">Embedding Model</p>
                <p className="text-white font-medium mt-1">all-MiniLM-L6-v2</p>
              </div>
              <div className="bg-[#18181b] border border-[#27272a] rounded-lg p-3">
                <p className="text-xs text-[#a1a1aa] uppercase tracking-wide font-medium">LLM</p>
                <p className="text-white font-medium mt-1">Gemini 2.5 Flash</p>
              </div>
            </div>
          </section>

          {/* Limits */}
          <section>
            <h3 className="text-lg font-semibold text-white mb-3">Limits & Constraints</h3>
            <div className="bg-[#18181b] border border-[#27272a] rounded-lg p-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[#a1a1aa]">Max file size:</span>
                <span className="text-white font-medium">50 MB</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#a1a1aa]">Max document content:</span>
                <span className="text-white font-medium">10 MB</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#a1a1aa]">Max query length:</span>
                <span className="text-white font-medium">5,000 characters</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#a1a1aa]">Chunk size:</span>
                <span className="text-white font-medium">500 words</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#a1a1aa]">Retrieval results:</span>
                <span className="text-white font-medium">Top 5 chunks</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#a1a1aa]">Rate limit:</span>
                <span className="text-white font-medium">60 requests/min per IP</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#a1a1aa]">Deletion behavior:</span>
                <span className="text-white font-medium">Postgres + Qdrant filter delete</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#a1a1aa]">Scanned PDFs:</span>
                <span className="text-white font-medium">OCR not enabled yet</span>
              </div>
            </div>
          </section>

          <section>
            <h3 className="text-lg font-semibold text-white mb-3">Reliability Notes</h3>
            <div className="space-y-2 text-sm text-[#a1a1aa] leading-relaxed">
              <p>Ingestion now rejects empty extracted content, preventing files from showing as indexed when no chunkable text exists.</p>
              <p>Qdrant delete-by-document uses payload indexing and includes retry logic for older collections missing the index.</p>
              <p>Configuration is environment-driven and tolerant of extra env keys to reduce local startup errors.</p>
            </div>
          </section>

          {/* Upcoming Features */}
          <section>
            <h3 className="text-lg font-semibold text-white mb-3">🚀 Upcoming Features</h3>
            <div className="space-y-2">
              <div className="flex gap-2">
                <span className="text-blue-400">▸</span>
                <span className="text-[#a1a1aa]"><strong className="text-white">Notion Workspace Sync</strong> — Auto-ingest your Notion databases</span>
              </div>
              <div className="flex gap-2">
                <span className="text-blue-400">▸</span>
                <span className="text-[#a1a1aa]"><strong className="text-white">Apple Notes Integration</strong> — Pull notes from local macOS Notes app</span>
              </div>
              <div className="flex gap-2">
                <span className="text-blue-400">▸</span>
                <span className="text-[#a1a1aa]"><strong className="text-white">Multi-turn Conversations</strong> — Chat context awareness for follow-up questions</span>
              </div>
              <div className="flex gap-2">
                <span className="text-blue-400">▸</span>
                <span className="text-[#a1a1aa]"><strong className="text-white">Custom Models</strong> — Swap Gemini for Claude, GPT-4, or local LLMs</span>
              </div>
              <div className="flex gap-2">
                <span className="text-blue-400">▸</span>
                <span className="text-[#a1a1aa]"><strong className="text-white">Real-time Collaboration</strong> — Share brain with team members</span>
              </div>
              <div className="flex gap-2">
                <span className="text-blue-400">▸</span>
                <span className="text-[#a1a1aa]"><strong className="text-white">Export & Analytics</strong> — Visualize knowledge graph and document stats</span>
              </div>
              <div className="flex gap-2">
                <span className="text-blue-400">▸</span>
                <span className="text-[#a1a1aa]"><strong className="text-white">Voice Query</strong> — Ask questions using voice commands</span>
              </div>
            </div>
          </section>

          {/* Tips */}
          <section>
            <h3 className="text-lg font-semibold text-white mb-3">💡 Tips</h3>
            <ul className="space-y-2 text-[#a1a1aa] text-sm">
              <li>• Use detailed note titles so they're easily identifiable in results</li>
              <li>• Ask specific questions for better answers (vs. vague queries)</li>
              <li>• Organize notes by topic/project for cleaner management</li>
              <li>• Check the "Qdrant Vector DB" status — green means your brain is ready!</li>
              <li>• Use Cmd/Ctrl+S in the notepad editor to save quickly</li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
