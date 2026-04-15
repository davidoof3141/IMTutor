import React, { useEffect, useState } from 'react';

export default function PdfViewer({ page: initialPage, onClose }) {
  const [page, setPage] = useState(initialPage);

  // Sync when parent changes the requested page
  useEffect(() => { setPage(initialPage); }, [initialPage]);

  // Close on Escape
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowRight') setPage(p => p + 1);
      if (e.key === 'ArrowLeft') setPage(p => Math.max(1, p - 1));
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  return (
    <>
      {/* Backdrop */}
      <div className="pdf-viewer-backdrop" onClick={onClose} />

      {/* Panel */}
      <div className="pdf-viewer-panel">
        {/* Header */}
        <div className="pdf-viewer-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '1rem' }}>📖</span>
            <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>
              Krcmar — Page {page}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button
              className="pdf-viewer-close"
              onClick={() => setPage(p => Math.max(1, p - 1))}
              title="Previous page (←)"
              style={{ fontSize: '0.75rem', width: 'auto', padding: '0 0.65rem' }}
            >
              ←
            </button>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', minWidth: '2rem', textAlign: 'center' }}>
              {page}
            </span>
            <button
              className="pdf-viewer-close"
              onClick={() => setPage(p => p + 1)}
              title="Next page (→)"
              style={{ fontSize: '0.75rem', width: 'auto', padding: '0 0.65rem' }}
            >
              →
            </button>
            <button
              className="pdf-viewer-close"
              onClick={onClose}
              aria-label="Close"
              style={{ marginLeft: '0.25rem' }}
            >
              ✕
            </button>
          </div>
        </div>

        {/* Page image */}
        <div style={{ flex: 1, overflowY: 'auto', background: '#e5e7eb', display: 'flex', justifyContent: 'center', padding: '1rem' }}>
          <img
            key={page}
            src={`/api/page-image/${page}`}
            alt={`Textbook page ${page}`}
            style={{
              maxWidth: '100%',
              height: 'auto',
              borderRadius: '4px',
              boxShadow: '0 4px 20px rgba(0,0,0,0.35)',
            }}
          />
        </div>
      </div>
    </>
  );
}
