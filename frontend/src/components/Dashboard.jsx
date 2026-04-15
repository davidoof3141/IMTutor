import React from 'react';
import { useAppContext } from '../context/AppContext';
import ChatInterface from './ChatInterface';

export default function Dashboard() {
  const {
    sidebarView, setSidebarView,
    conversations, currentConversationId, setCurrentConversationId, createNewChat,
    bookData, learnerStats,
  } = useAppContext();

  const handleSelectSubchapter = (chapterId, subchapterId, subchapterTitle) => {
    const existingChat = conversations.find(c => c.type === 'subchapter' && c.targetId === subchapterId);
    if (existingChat) {
      setCurrentConversationId(existingChat.id);
    } else {
      createNewChat('subchapter', subchapterId, subchapterTitle);
    }
  };

  const handleCreateGeneralChat = () => {
    createNewChat('general', null, 'New Chat');
  };

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', padding: '1rem', gap: '1rem' }}>

      {/* Sidebar */}
      <div className="glass-panel" style={{ width: '300px', display: 'flex', flexDirection: 'column', padding: '1rem', overflowY: 'auto' }}>

        {/* Toggle */}
        <div style={{
          display: 'flex',
          background: 'var(--bg-base)',
          padding: '0.25rem',
          borderRadius: '50px',
          border: '1px solid var(--border-subtle)',
          marginBottom: '1rem',
        }}>
          {['history', 'curriculum'].map(view => (
            <button
              key={view}
              style={{
                flex: 1,
                borderRadius: '50px',
                padding: '0.5rem',
                border: 'none',
                background: sidebarView === view ? 'var(--accent-primary)' : 'transparent',
                color: sidebarView === view ? 'white' : 'var(--text-secondary)',
                cursor: 'pointer',
                fontWeight: 500,
                transition: 'all 0.2s',
                fontSize: '0.85rem',
                textTransform: 'capitalize',
              }}
              onClick={() => setSidebarView(view)}
            >
              {view}
            </button>
          ))}
        </div>

        {/* History View */}
        {sidebarView === 'history' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <button
              className="btn btn-secondary"
              style={{ width: '100%', marginBottom: '1rem', borderStyle: 'dashed' }}
              onClick={handleCreateGeneralChat}
            >
              + New Chat
            </button>

            {conversations.map(chat => {
              const isActive = chat.id === currentConversationId;
              return (
                <div
                  key={chat.id}
                  onClick={() => setCurrentConversationId(chat.id)}
                  style={{
                    padding: '0.75rem',
                    borderRadius: '8px',
                    background: isActive ? 'var(--bg-elevated)' : 'transparent',
                    border: `1px solid ${isActive ? 'var(--accent-secondary)' : 'transparent'}`,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    color: isActive ? 'white' : 'var(--text-secondary)',
                  }}
                >
                  {chat.type === 'subchapter' ? '📚 ' : '💬 '} {chat.title}
                </div>
              );
            })}
          </div>
        )}

        {/* Curriculum View */}
        {sidebarView === 'curriculum' && (
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {!bookData ? (
              <div style={{ color: 'var(--text-secondary)' }}>Loading Curriculum...</div>
            ) : (
              bookData.chapters.map(chapter => (
                <div key={chapter.id} style={{ marginBottom: '1rem' }}>
                  <h4 style={{ fontSize: '0.95rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                    {chapter.title}
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {chapter.subchapters.map(sub => {
                      const score = learnerStats[sub.id]?.score || 0;
                      return (
                        <div
                          key={sub.id}
                          onClick={() => handleSelectSubchapter(chapter.id, sub.id, sub.title)}
                          style={{
                            padding: '0.75rem',
                            borderRadius: '8px',
                            background: 'var(--bg-elevated)',
                            border: '1px solid var(--border-subtle)',
                            cursor: 'pointer',
                            transition: 'all 0.2s',
                          }}
                          onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent-primary)'; }}
                          onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border-subtle)'; }}
                        >
                          <div style={{ fontSize: '0.85rem' }}>{sub.title}</div>
                          <div style={{ marginTop: '0.5rem', height: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{ width: `${score}%`, height: '100%', background: score === 100 ? 'var(--success)' : 'var(--accent-secondary)' }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Main Chat */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <ChatInterface />
      </div>

    </div>
  );
}
