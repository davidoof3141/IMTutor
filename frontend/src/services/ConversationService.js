export const processMessage = async (message, context) => {
  const { preferences, chatType, targetId, learnerState } = context.getEffectiveControls();
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, chatType, targetId, preferences, learnerState: learnerState || {} }),
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error("Error communicating with backend:", error);
    return { text: "Sorry, I am having trouble connecting to my backend brain right now.", kcs: [], suggestions: [], page_refs: [], intent: "error" };
  }
};

export const fetchChapterSummary = async (targetId, preferences) => {
  try {
    const response = await fetch('/api/chapter-summary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targetId, preferences }),
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error("Error fetching chapter summary:", error);
    return { text: "Sorry, I couldn't load the chapter summary right now.", suggestions: [], kcs: [] };
  }
};

export const fetchLearningPlan = async (targetId, preferences) => {
  try {
    const response = await fetch('/api/learning-plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targetId, preferences }),
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error("Error fetching learning plan:", error);
    return { text: "Sorry, I couldn't generate a learning plan right now.", steps: [], suggestions: [], kcs: [] };
  }
};

export const fetchStepContent = async (subId, stepTitle, preferences) => {
  try {
    const response = await fetch('/api/step-content', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subId, stepTitle, preferences }),
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error("Error fetching step content:", error);
    return { text: "Sorry, I couldn't load the step content.", page_refs: [], suggestions: [], kcs: [] };
  }
};
