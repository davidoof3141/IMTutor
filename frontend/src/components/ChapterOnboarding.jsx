import React, { useState } from 'react';

const selectStyle = {
  width: '100%',
  padding: '0.75rem',
  borderRadius: '8px',
  background: 'var(--bg-base)',
  color: 'white',
  border: '1px solid var(--border-subtle)',
  marginBottom: '1rem',
};

const labelStyle = {
  display: 'block',
  marginBottom: '0.4rem',
  fontWeight: 500,
  fontSize: '0.9rem',
};

export default function ChapterOnboarding({ chapterTitle, onComplete, onSkip }) {
  const [values, setValues] = useState({
    topicFamiliarity: 'new',
    relevance: 'general',
    specificInterest: 'entire',
    confidenceLevel: 'deep',
  });

  const set = (key, val) => setValues(prev => ({ ...prev, [key]: val }));

  return (
    <div style={{
      position: 'fixed', inset: 0,
      background: 'rgba(0,0,0,0.65)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
      padding: '1rem',
    }}>
      <div className="glass-panel animate-fade-in" style={{ maxWidth: '480px', width: '100%', padding: '2rem' }}>

        <div style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: '1.25rem', marginBottom: '0.25rem' }}>Chapter Check-in</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            A few quick questions about <strong style={{ color: 'var(--text-primary)' }}>{chapterTitle}</strong> to personalise this session.
          </p>
        </div>

        <div>
          <label style={labelStyle}>Your familiarity with this topic</label>
          <select value={values.topicFamiliarity} onChange={e => set('topicFamiliarity', e.target.value)} style={selectStyle}>
            <option value="new">New to this — first time encountering it</option>
            <option value="some">Some exposure — heard of it, not used it</option>
            <option value="practitioner">Daily practitioner — use it regularly</option>
          </select>
        </div>

        <div>
          <label style={labelStyle}>Relevance to your current work</label>
          <select value={values.relevance} onChange={e => set('relevance', e.target.value)} style={selectStyle}>
            <option value="urgent">Urgent need — applying it right now</option>
            <option value="future">Future planning — relevant soon</option>
            <option value="general">General knowledge — no immediate need</option>
          </select>
        </div>

        <div>
          <label style={labelStyle}>What do you want to cover?</label>
          <select value={values.specificInterest} onChange={e => set('specificInterest', e.target.value)} style={selectStyle}>
            <option value="entire">Entire chapter</option>
            <option value="overview">High-level overview only</option>
            <option value="practical">Practical / application parts</option>
            <option value="theory">Theory and foundations</option>
          </select>
        </div>

        <div>
          <label style={labelStyle}>Your learning goal for this chapter</label>
          <select value={values.confidenceLevel} onChange={e => set('confidenceLevel', e.target.value)} style={selectStyle}>
            <option value="deep">Learn deeply — thorough explanations</option>
            <option value="refresher">Refresher — remind me of key points</option>
            <option value="validate">Validate knowledge — I think I know it</option>
          </select>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
          <button
            className="btn btn-secondary"
            style={{ flex: 1, padding: '0.85rem' }}
            onClick={onSkip}
          >
            Skip
          </button>
          <button
            className="btn btn-primary"
            style={{ flex: 1, padding: '0.85rem' }}
            onClick={() => onComplete(values)}
          >
            Start Chapter
          </button>
        </div>
      </div>
    </div>
  );
}
