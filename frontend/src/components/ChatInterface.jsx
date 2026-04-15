import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAppContext } from '../context/AppContext';
import { processMessage, fetchChapterSummary, fetchLearningPlan, fetchStepContent } from '../services/ConversationService';
import ChapterOnboarding from './ChapterOnboarding';
import PdfViewer from './PdfViewer';

// Banner shown on general-chat messages when the topic maps to curriculum sections
function CurriculumMatchBanner({ matches, onNavigate, onDismiss }) {
  if (!matches || matches.length === 0) return null;
  return (
    <div style={{
      marginTop: '0.75rem',
      padding: '0.7rem 0.9rem',
      background: 'rgba(139, 92, 246, 0.08)',
      border: '1px solid rgba(139, 92, 246, 0.28)',
      borderRadius: '8px',
    }}>
      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
        📚 This topic is covered in the curriculum:
      </div>
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
        {matches.map(m => (
          <button
            key={m.id}
            onClick={() => onNavigate(m)}
            style={{
              padding: '0.35rem 0.85rem',
              borderRadius: '20px',
              background: 'rgba(139, 92, 246, 0.15)',
              border: '1px solid rgba(139, 92, 246, 0.45)',
              color: 'var(--text-primary)',
              cursor: 'pointer',
              fontSize: '0.82rem',
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(139, 92, 246, 0.3)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(139, 92, 246, 0.15)'; }}
          >
            📖 {m.title}
          </button>
        ))}
        <button
          onClick={onDismiss}
          style={{
            padding: '0.35rem 0.85rem',
            borderRadius: '20px',
            background: 'transparent',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
            fontSize: '0.82rem',
            transition: 'all 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.3)'; e.currentTarget.style.color = 'var(--text-primary)'; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.15)'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
        >
          Stay in General Chat
        </button>
      </div>
    </div>
  );
}

// Chips shown below bot messages for follow-up prompts
function SuggestionChips({ suggestions, onSelect }) {
  if (!suggestions || suggestions.length === 0) return null;
  return (
    <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
      {suggestions.map((s, i) => (
        <button
          key={i}
          onClick={() => onSelect(s)}
          style={{
            padding: '0.35rem 0.85rem',
            borderRadius: '20px',
            background: 'rgba(139, 92, 246, 0.12)',
            border: '1px solid rgba(139, 92, 246, 0.35)',
            color: 'var(--text-primary)',
            cursor: 'pointer',
            fontSize: '0.82rem',
            transition: 'all 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'rgba(139, 92, 246, 0.25)'; }}
          onMouseLeave={e => { e.currentTarget.style.background = 'rgba(139, 92, 246, 0.12)'; }}
        >
          {s}
        </button>
      ))}
    </div>
  );
}

// Collapsible strip of textbook page thumbnails — click to open PDF viewer
function PageImageStrip({ pageRefs, onPageClick }) {
  const [open, setOpen] = useState(false);
  if (!pageRefs || pageRefs.length === 0) return null;
  return (
    <div style={{ marginTop: '0.75rem' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: 'rgba(59,130,246,0.12)',
          border: '1px solid rgba(59,130,246,0.3)',
          borderRadius: '20px',
          color: 'var(--text-secondary)',
          fontSize: '0.8rem',
          padding: '0.3rem 0.8rem',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '0.4rem',
        }}
      >
        📖 {open ? 'Hide' : 'Show'} textbook page{pageRefs.length > 1 ? 's' : ''} ({pageRefs.join(', ')})
      </button>
      {open && (
        <div style={{ display: 'flex', gap: '0.75rem', overflowX: 'auto', marginTop: '0.75rem', paddingBottom: '0.5rem' }}>
          {pageRefs.map(p => (
            <div
              key={p}
              onClick={() => onPageClick(p)}
              style={{ flexShrink: 0, cursor: 'pointer' }}
              title={`Open page ${p} in PDF viewer`}
            >
              <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '0.25rem', textAlign: 'center' }}>
                Page {p}
              </div>
              <img
                src={`/api/page-image/${p}`}
                alt={`Textbook page ${p}`}
                style={{
                  height: '280px',
                  width: 'auto',
                  borderRadius: '6px',
                  border: '1px solid rgba(59,130,246,0.4)',
                  boxShadow: '0 0 0 0 rgba(59,130,246,0)',
                  background: '#fff',
                  transition: 'box-shadow 0.15s, border-color 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 0 10px rgba(59,130,246,0.4)'; }}
                onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; }}
              />
              <div style={{ fontSize: '0.68rem', color: 'var(--accent-secondary)', textAlign: 'center', marginTop: '0.2rem' }}>
                click to open →
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Single figure card — renders a figure-specific image where available
function FigureCard({ fig, onPageClick }) {
  const figureSrc = fig?.ref_key
    ? `/api/figure-ref/${encodeURIComponent(fig.ref_key)}`
    : `/api/page-image/${fig.page}`;

  return (
    <div
      onClick={() => onPageClick(fig.page)}
      title={`Open page ${fig.page} in PDF viewer`}
      style={{
        margin: '0.85rem 0',
        background: 'var(--bg-base)',
        border: '1px solid var(--border-subtle)',
        borderRadius: '8px',
        overflow: 'hidden',
        maxWidth: '480px',
        cursor: 'pointer',
        transition: 'border-color 0.15s, box-shadow 0.15s',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'var(--accent-secondary)';
        e.currentTarget.style.boxShadow = '0 0 12px rgba(59,130,246,0.2)';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = 'var(--border-subtle)';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      <img
        src={figureSrc}
        alt={fig.caption || `Figure on page ${fig.page}`}
        style={{ width: '100%', height: 'auto', display: 'block', background: '#fff' }}
      />
      <div style={{
        padding: '0.45rem 0.7rem',
        fontSize: '0.74rem',
        color: 'var(--text-secondary)',
        borderTop: '1px solid var(--border-subtle)',
        lineHeight: 1.4,
      }}>
        {fig.caption || fig.ref}
      </div>
      <div style={{ padding: '0.2rem 0.7rem 0.4rem', fontSize: '0.69rem', color: 'var(--accent-secondary)' }}>
        📖 p. {fig.page} — click to open in PDF viewer
      </div>
    </div>
  );
}

// Renders markdown with inline figures injected after the paragraph that first references them
function MessageContent({ text, figures, onPageClick }) {
  // Build lookup by the "ref" field: "Abb. 3.1" -> figure object
  const figureByRef = {};
  (figures || []).forEach(fig => {
    if (fig.ref) figureByRef[fig.ref] = fig;
  });
  const hasFigures = Object.keys(figureByRef).length > 0;

  // Custom link renderer: intercepts #page-N hrefs
  const components = {
    a: ({ href, children, ...props }) => {
      const pageMatch = href?.match(/^#page-(\d+)$/);
      if (pageMatch) {
        return (
          <button
            className="page-ref-link"
            onClick={() => onPageClick(Number(pageMatch[1]))}
            title={`Open page ${pageMatch[1]} in PDF viewer`}
          >
            📖 p. {pageMatch[1]}
          </button>
        );
      }
      return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
    },
  };

  if (!hasFigures) {
    return <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{text}</ReactMarkdown>;
  }

  // Split into paragraph chunks, inject the matching figure card after the first
  // paragraph that mentions each "Abb. X.Y"
  const usedFigs = new Set();
  const chunks = text.split(/\n\n+/);
  const segments = [];

  chunks.forEach((chunk, i) => {
    segments.push({ type: 'md', content: chunk, key: `md-${i}` });
    for (const [abbRef, fig] of Object.entries(figureByRef)) {
      // Match "Abb. 3.1" or "Abb.3.1"
      const pattern = abbRef.replace('.', '\\.').replace(' ', '\\s*');
      if (!usedFigs.has(abbRef) && new RegExp(pattern).test(chunk)) {
        usedFigs.add(abbRef);
        segments.push({ type: 'figure', fig, key: `fig-${abbRef}` });
      }
    }
  });

  return (
    <>
      {segments.map(seg =>
        seg.type === 'figure'
          ? <FigureCard key={seg.key} fig={seg.fig} onPageClick={onPageClick} />
          : <ReactMarkdown key={seg.key} remarkPlugins={[remarkGfm]} components={components}>{seg.content}</ReactMarkdown>
      )}
    </>
  );
}

export default function ChatInterface() {
  const context = useAppContext();
  const {
    conversations, currentConversationId,
    addMessageToChat, removeActionsFromMessage, updateConversationTitle,
    preferences, setChapterPrefsForId,
    bookData,
    getEffectiveControls,
    createNewChat,
  } = context;

  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showChapterOnboarding, setShowChapterOnboarding] = useState(false);
  const [pdfViewerPage, setPdfViewerPage] = useState(null);
  const [dismissedMatches, setDismissedMatches] = useState(new Set());
  const scrollRef = useRef(null);

  // Reset dismissed banners when switching conversations
  useEffect(() => {
    setDismissedMatches(new Set());
  }, [currentConversationId]);


  const activeChat = conversations.find(c => c.id === currentConversationId);
  const messages = activeChat ? activeChat.messages : [];

  const chapterId = activeChat?.targetId ? activeChat.targetId.split('.')[0] : null;
  const chapterTitle = chapterId
    ? bookData?.chapters.find(c => c.id === chapterId)?.title || chapterId
    : null;

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, isTyping]);

  useEffect(() => {
    setShowChapterOnboarding(false);
  }, [currentConversationId]);

  // -------------------------------------------------------------------------
  // Sending a user message
  // -------------------------------------------------------------------------
  const sendUserMessage = async (text) => {
    if (!text.trim() || !activeChat) return;
    const userMsg = { role: 'user', text };
    addMessageToChat(currentConversationId, userMsg);

    // Set conversation title from the first user message in general chat
    const isDefaultTitle = activeChat.title === 'General Chat' || activeChat.title === 'New Chat';
    const hasNoUserMessages = !activeChat.messages.some(m => m.role === 'user');
    if (activeChat.type === 'general' && isDefaultTitle && hasNoUserMessages) {
      const title = text.length > 45 ? text.slice(0, 42).trimEnd() + '…' : text;
      updateConversationTitle(currentConversationId, title);
    }

    setInput('');
    setIsTyping(true);
    const botResponse = await processMessage(text, context);
    addMessageToChat(currentConversationId, {
      role: 'bot',
      text: botResponse.text,
      kcs: botResponse.kcs || [],
      suggestions: botResponse.suggestions || [],
      page_refs: botResponse.page_refs || [],
      figures: botResponse.figures || [],
      curriculum_matches: botResponse.curriculum_matches || [],
    });
    setIsTyping(false);
  };

  const handleSend = () => sendUserMessage(input);

  // -------------------------------------------------------------------------
  // Learning plan helper — also used after onboarding complete/skip
  // -------------------------------------------------------------------------
  const sendLearningPlan = async (chapterPrefsData) => {
    setIsTyping(true);
    const effectivePrefs = chapterPrefsData
      ? { ...preferences, ...chapterPrefsData }
      : getEffectiveControls().preferences;

    const result = await fetchLearningPlan(activeChat.targetId, effectivePrefs);

    // Convert steps into action buttons
    const stepActions = (result.steps || []).map(step => ({
      id: `step-${step.index}`,
      label: `▶ Step ${step.index + 1}: ${step.title.replace(/^\d+\.\d+(\.\d+)?\s*/, '')}`,
      variant: 'secondary',
      data: { subId: step.subId, title: step.title },
    }));

    addMessageToChat(currentConversationId, {
      role: 'bot',
      text: result.text,
      kcs: result.kcs || [],
      suggestions: result.suggestions || [],
      actions: stepActions,
    });
    setIsTyping(false);
  };

  // -------------------------------------------------------------------------
  // Action button handler
  // -------------------------------------------------------------------------
  const handleAction = async (msgIndex, action) => {
    removeActionsFromMessage(currentConversationId, msgIndex);
    const { id: actionId } = action;

    if (actionId === 'start-chapter') {
      setIsTyping(true);
      const result = await fetchChapterSummary(activeChat.targetId, getEffectiveControls().preferences);
      addMessageToChat(currentConversationId, {
        role: 'bot',
        text: result.text,
        kcs: [],
        plain: true,
        actions: [
          { id: 'personalize', label: 'Personalise for this chapter', variant: 'primary' },
          { id: 'skip-to-plan', label: 'Skip — use my global settings', variant: 'secondary' },
        ],
      });
      setIsTyping(false);

    } else if (actionId === 'personalize') {
      setShowChapterOnboarding(true);

    } else if (actionId === 'skip-to-plan') {
      await sendLearningPlan(null);

    } else if (actionId.startsWith('step-')) {
      const { subId, title } = action.data || {};
      if (!subId) return;
      setIsTyping(true);
      const effectivePrefs = getEffectiveControls().preferences;
      const result = await fetchStepContent(subId, title, effectivePrefs);
      addMessageToChat(currentConversationId, {
        role: 'bot',
        text: result.text,
        kcs: result.kcs || [],
        page_refs: result.page_refs || [],
        figures: result.figures || [],
        suggestions: result.suggestions || [],
      });
      setIsTyping(false);
    }
  };

  // -------------------------------------------------------------------------
  // Chapter onboarding handlers
  // -------------------------------------------------------------------------
  const handleChapterOnboardingComplete = async (data) => {
    setShowChapterOnboarding(false);
    if (chapterId) setChapterPrefsForId(chapterId, data);
    await sendLearningPlan(data);
  };

  const handleChapterOnboardingSkip = async () => {
    setShowChapterOnboarding(false);
    await sendLearningPlan(null);
  };

  const handleNavigateToSection = (section) => {
    createNewChat('subchapter', section.id, section.title);
  };

  const handleDismissCurriculumMatches = (msgIndex) => {
    setDismissedMatches(prev => new Set([...prev, msgIndex]));
  };

  if (!activeChat) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-secondary)' }}>
        Select or create a conversation.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {showChapterOnboarding && (
        <ChapterOnboarding
          chapterTitle={chapterTitle}
          onComplete={handleChapterOnboardingComplete}
          onSkip={handleChapterOnboardingSkip}
        />
      )}

      {/* Top Bar */}
      <div className="glass-panel" style={{ padding: '1rem', marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem' }}>{activeChat.type === 'subchapter' ? '📚 ' : '💬 '}{activeChat.title}</h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            {activeChat.type === 'general' ? 'General Purpose Assistance' : 'Structured Curriculum Learning'}
          </p>
        </div>
      </div>

      {/* Chat History */}
      <div
        className="glass-panel"
        style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}
        ref={scrollRef}
      >
        {messages.map((msg, i) => (
          <div
            key={i}
            className="animate-fade-in"
            style={{ alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '82%' }}
          >
            {/* Message bubble */}
            <div
              className={msg.role === 'bot' ? 'markdown-body' : undefined}
              style={{
                background: msg.role === 'user'
                  ? 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))'
                  : 'var(--bg-elevated)',
                padding: '1rem',
                borderRadius: 'var(--border-radius-sm)',
                boxShadow: 'var(--shadow-sm)',
                border: msg.role === 'bot' ? '1px solid var(--border-subtle)' : 'none',
              }}
            >
              {msg.role === 'bot'
                ? <MessageContent
                    text={msg.text}
                    figures={msg.plain ? [] : (msg.figures || [])}
                    onPageClick={setPdfViewerPage}
                  />
                : <span>{msg.text}</span>
              }
            </div>

            {/* Textbook page thumbnails */}
            {msg.role === 'bot' && !msg.plain && <PageImageStrip pageRefs={msg.page_refs} onPageClick={setPdfViewerPage} />}

            {/* Action buttons */}
            {msg.actions && msg.actions.length > 0 && (
              <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
                {msg.actions.map(action => (
                  <button
                    key={action.id}
                    className={action.variant === 'primary' ? 'btn btn-primary' : 'btn btn-secondary'}
                    style={{ padding: '0.6rem 1.25rem', fontSize: '0.88rem' }}
                    onClick={() => handleAction(i, action)}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            )}

            {/* Suggestion chips */}
            {msg.role === 'bot' && !msg.plain && (
              <SuggestionChips
                suggestions={msg.suggestions}
                onSelect={(s) => sendUserMessage(s)}
              />
            )}

            {/* Curriculum section links — general chat only */}
            {msg.role === 'bot' && activeChat.type === 'general' && !dismissedMatches.has(i) && (
              <CurriculumMatchBanner
                matches={msg.curriculum_matches}
                onNavigate={handleNavigateToSection}
                onDismiss={() => handleDismissCurriculumMatches(i)}
              />
            )}

            {/* KC Tags */}
            {msg.kcs && msg.kcs.length > 0 && (
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                {msg.kcs.map((kc, idx) => (
                  <span key={idx} style={{ fontSize: '0.75rem', background: 'var(--accent-glow)', padding: '0.2rem 0.5rem', borderRadius: '1rem', color: 'var(--text-primary)' }}>
                    #{kc}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}

        {isTyping && (
          <div className="animate-fade-in" style={{ alignSelf: 'flex-start', background: 'var(--bg-elevated)', padding: '1rem', borderRadius: 'var(--border-radius-sm)' }}>
            <span style={{ fontStyle: 'italic', color: 'var(--text-secondary)' }}>AI is typing…</span>
          </div>
        )}
      </div>

      {/* Input Area */}
      <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem' }}>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder={activeChat.type === 'general' ? 'Ask any question…' : 'Ask a question about this topic…'}
          style={{ flex: 1, padding: '1rem', borderRadius: 'var(--border-radius-sm)', background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', color: 'white', outline: 'none' }}
        />
        <button className="btn btn-primary" onClick={handleSend} style={{ padding: '1rem 2rem' }}>
          Send
        </button>
      </div>
      {/* PDF Viewer */}
      {pdfViewerPage !== null && (
        <PdfViewer page={pdfViewerPage} onClose={() => setPdfViewerPage(null)} />
      )}
    </div>
  );
}
