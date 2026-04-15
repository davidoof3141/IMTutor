import React, { useState } from 'react';
import { useAppContext } from '../context/AppContext';

const STEPS = [
  {
    title: 'Who are you?',
    fields: [
      {
        key: 'role',
        label: 'Your Role / Responsibility',
        options: [
          { value: 'CIO', label: 'CIO' },
          { value: 'IT Manager', label: 'IT Manager' },
          { value: 'Business Unit Leader', label: 'Business Unit Leader' },
          { value: 'Consultant', label: 'Consultant' },
          { value: 'Student', label: 'Student' },
          { value: 'Other', label: 'Other' },
        ],
      },
      {
        key: 'globalCompetency',
        label: 'IS/IT Expertise Level',
        options: [
          { value: 'novice', label: 'Novice — little to no prior knowledge' },
          { value: 'intermediate', label: 'Intermediate — some practical experience' },
          { value: 'expert', label: 'Expert — deep domain knowledge' },
        ],
      },
      {
        key: 'industry',
        label: 'Your Industry',
        options: [
          { value: 'Healthcare', label: 'Healthcare' },
          { value: 'Finance', label: 'Finance' },
          { value: 'Manufacturing', label: 'Manufacturing' },
          { value: 'Retail', label: 'Retail' },
          { value: 'Public Sector', label: 'Public Sector' },
          { value: 'IT/Tech', label: 'IT / Tech' },
          { value: 'Other', label: 'Other' },
        ],
      },
    ],
  },
  {
    title: 'Your context',
    fields: [
      {
        key: 'orgSize',
        label: 'Organisation Size',
        options: [
          { value: 'SMB', label: 'SMB (< 250 employees)' },
          { value: 'Mittelstand', label: 'Mittelstand (250–3 000)' },
          { value: 'Enterprise', label: 'Enterprise (> 3 000)' },
        ],
      },
      {
        key: 'learningGoal',
        label: 'Learning Goal',
        options: [
          { value: 'certification', label: 'Certification prep' },
          { value: 'practical', label: 'Practical application' },
          { value: 'strategic', label: 'Strategic overview' },
          { value: 'problem-solving', label: 'Problem-solving' },
        ],
      },
      {
        key: 'timeAvailability',
        label: 'Time Availability per Session',
        options: [
          { value: 'quick', label: 'Quick (10–15 min)' },
          { value: 'standard', label: 'Standard (30 min)' },
          { value: 'deep-dive', label: 'Deep-dive (60+ min)' },
        ],
      },
    ],
  },
  {
    title: 'Learning style',
    fields: [
      {
        key: 'learnerType',
        label: 'Preferred Learning Style',
        options: [
          { value: 'visual', label: 'Visual — diagrams, charts' },
          { value: 'reading', label: 'Reading — text, summaries' },
          { value: 'auditory', label: 'Auditory — explanations, analogies' },
          { value: 'kinesthetic', label: 'Kinesthetic — examples, exercises' },
        ],
      },
      {
        key: 'languagePreference',
        label: 'Language Preference',
        options: [
          { value: 'german', label: 'Full German' },
          { value: 'german-en-terms', label: 'German with English IT terms' },
          { value: 'bilingual', label: 'Bilingual (DE + EN)' },
        ],
      },
      {
        key: 'tone',
        label: 'Preferred Tone',
        options: [
          { value: 'professional', label: 'Professional & Direct' },
          { value: 'casual', label: 'Casual & Conversational' },
          { value: 'academic', label: 'Academic & Theoretical' },
        ],
      },
      {
        key: 'format',
        label: 'Didactic Format',
        options: [
          { value: 'standard', label: 'Standard Explanations' },
          { value: 'socratic', label: 'Socratic (Questioning)' },
          { value: 'step-by-step', label: 'Step-by-step Breakdown' },
        ],
      },
    ],
  },
];

const DEFAULTS = {
  role: 'Other',
  globalCompetency: 'intermediate',
  industry: 'IT/Tech',
  orgSize: 'Enterprise',
  learningGoal: 'practical',
  timeAvailability: 'standard',
  learnerType: 'reading',
  languagePreference: 'bilingual',
  tone: 'professional',
  format: 'standard',
};

const selectStyle = {
  width: '100%',
  padding: '0.75rem',
  borderRadius: '8px',
  background: 'var(--bg-elevated)',
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

export default function Onboarding() {
  const { setIsOnboarded, setPreferences } = useAppContext();
  const [step, setStep] = useState(0);
  const [values, setValues] = useState(DEFAULTS);

  const currentStep = STEPS[step];
  const isLast = step === STEPS.length - 1;

  const set = (key, val) => setValues(prev => ({ ...prev, [key]: val }));

  const handleNext = () => {
    if (isLast) {
      setPreferences(values);
      setIsOnboarded(true);
    } else {
      setStep(s => s + 1);
    }
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', padding: '1rem' }}>
      <div className="glass-panel animate-fade-in" style={{ maxWidth: '520px', width: '100%', padding: '2.5rem' }}>

        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <h1 className="text-gradient" style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>Welcome to InfoSys</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Set up your Intelligent Learner Profile</p>
        </div>

        {/* Step indicator */}
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.75rem', justifyContent: 'center' }}>
          {STEPS.map((s, i) => (
            <div key={i} style={{
              height: '4px',
              flex: 1,
              borderRadius: '2px',
              background: i <= step ? 'var(--accent-primary)' : 'var(--border-subtle)',
              transition: 'background 0.3s',
            }} />
          ))}
        </div>

        {/* Step title */}
        <h3 style={{ marginBottom: '1.25rem', fontSize: '1rem', color: 'var(--text-secondary)' }}>
          Step {step + 1} of {STEPS.length}: {currentStep.title}
        </h3>

        {/* Fields */}
        {currentStep.fields.map(field => (
          <div key={field.key}>
            <label style={labelStyle}>{field.label}</label>
            <select
              value={values[field.key]}
              onChange={e => set(field.key, e.target.value)}
              style={selectStyle}
            >
              {field.options.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        ))}

        {/* Navigation */}
        <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
          {step > 0 && (
            <button
              className="btn btn-secondary"
              style={{ flex: 1, padding: '0.9rem' }}
              onClick={() => setStep(s => s - 1)}
            >
              Back
            </button>
          )}
          <button
            className="btn btn-primary"
            style={{ flex: 1, padding: '0.9rem', fontSize: '1rem' }}
            onClick={handleNext}
          >
            {isLast ? 'Start Learning' : 'Next'}
          </button>
        </div>
      </div>
    </div>
  );
}
