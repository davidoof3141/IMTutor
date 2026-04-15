import React, { createContext, useContext, useState, useEffect } from 'react';
import { initialMerillState } from '../data/mockBookData';

const AppContext = createContext();

export const AppProvider = ({ children }) => {
  // --- Global App State ---
  const [isOnboarded, setIsOnboarded] = useState(false);
  const [preferences, setPreferences] = useState({
    tone: 'professional',
    format: 'standard',
    learnerType: 'reading',
    globalCompetency: 'intermediate',
    industry: 'IT/Tech',
    orgSize: 'Enterprise',
    role: 'Other',
    learningGoal: 'practical',
    timeAvailability: 'standard',
    languagePreference: 'bilingual',
  });

  // --- Tier 2: Per-chapter prefs (set after chapter onboarding inside chat) ---
  // { [chapterId]: { topicFamiliarity, relevance, specificInterest, confidenceLevel } }
  const [chapterPrefs, setChapterPrefs] = useState({});

  const setChapterPrefsForId = (chapterId, data) => {
    setChapterPrefs(prev => ({ ...prev, [chapterId]: data }));
  };

  // --- Backend Data ---
  const [bookData, setBookData] = useState(null);

  useEffect(() => {
    fetch('/api/curriculum')
      .then(res => res.json())
      .then(data => setBookData(data))
      .catch(err => console.error("Failed to load backend curriculum", err));
  }, []);

  // --- Sidebar & Navigation ---
  const [sidebarView, setSidebarView] = useState('history');

  // --- Conversations ---
  const [conversations, setConversations] = useState([
    {
      id: 'default-1',
      type: 'general',
      targetId: null,
      title: 'General Chat',
      messages: [{ role: 'bot', text: 'Welcome! I am your AI assistant running on a Full-Stack Python backend. How can I help you today?', kcs: [] }]
    }
  ]);
  const [currentConversationId, setCurrentConversationId] = useState('default-1');

  const createNewChat = (type = 'general', targetId = null, title = 'New Chat') => {
    const newId = 'chat-' + Math.random().toString(36).substr(2, 9);

    let initialMessage;
    if (type === 'subchapter' && bookData) {
      const subchapterName = bookData.chapters
        .flatMap(c => c.subchapters)
        .find(s => s.id === targetId)?.title || 'this topic';
      initialMessage = {
        role: 'bot',
        text: `Ready to explore **${subchapterName}**.\n\nClick **Start Chapter** to get a brief overview, then I'll build your personalised learning plan.`,
        kcs: [],
        actions: [{ id: 'start-chapter', label: 'Start Chapter', variant: 'primary' }],
      };
    } else {
      initialMessage = { role: 'bot', text: 'How can I assist you today?', kcs: [] };
    }

    const newChat = { id: newId, type, targetId, title, messages: [initialMessage] };
    setConversations(prev => [newChat, ...prev]);
    setCurrentConversationId(newId);
  };

  const addMessageToChat = (chatId, messageObj) => {
    setConversations(prev => prev.map(chat =>
      chat.id === chatId ? { ...chat, messages: [...chat.messages, messageObj] } : chat
    ));
  };

  const updateConversationTitle = (chatId, title) => {
    setConversations(prev => prev.map(chat =>
      chat.id === chatId ? { ...chat, title } : chat
    ));
  };

  const removeActionsFromMessage = (chatId, msgIndex) => {
    setConversations(prev => prev.map(chat => {
      if (chat.id !== chatId) return chat;
      const newMessages = chat.messages.map((msg, i) => {
        if (i !== msgIndex) return msg;
        const { actions, ...rest } = msg;
        return rest;
      });
      return { ...chat, messages: newMessages };
    }));
  };

  // --- Dynamic Learner Profile ---
  const [learnerStats, setLearnerStats] = useState({});

  const updateLearnerStat = (subchapterId, field, value) => {
    setLearnerStats(prev => {
      const current = prev[subchapterId] || { score: 0, merill: { ...initialMerillState } };
      if (field === 'score') return { ...prev, [subchapterId]: { ...current, score: value } };
      if (field === 'merill') return { ...prev, [subchapterId]: { ...current, merill: { ...current.merill, ...value } } };
      return prev;
    });
  };

  const overrideControls = (newOverrides) => {
    setPreferences(prev => ({ ...prev, ...newOverrides }));
  };

  const getEffectiveControls = () => {
    const currentChat = conversations.find(c => c.id === currentConversationId);
    const targetId = currentChat?.targetId;
    // "ch3.1" → "ch3"
    const chapterId = targetId ? targetId.split('.')[0] : null;
    const storedChapterPrefs = chapterId ? (chapterPrefs[chapterId] || {}) : {};

    return {
      preferences: { ...preferences, ...storedChapterPrefs },
      chatType: currentChat?.type || 'general',
      targetId,
      learnerState: targetId ? (learnerStats[targetId] || null) : null,
    };
  };

  const contextValue = {
    isOnboarded, setIsOnboarded,
    preferences, setPreferences,
    chapterPrefs, setChapterPrefsForId,
    sidebarView, setSidebarView,
    conversations, setConversations,
    currentConversationId, setCurrentConversationId,
    createNewChat, addMessageToChat, removeActionsFromMessage, updateConversationTitle,
    learnerStats, updateLearnerStat,
    bookData,
    overrideControls,
    getEffectiveControls,
  };

  return (
    <AppContext.Provider value={contextValue}>
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => useContext(AppContext);
