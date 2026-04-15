export const mockBookGraph = {
  bookTitle: "Information Systems Management",
  author: "Krcmar",
  chapters: [
    {
      id: "ch1",
      title: "1. Information and Communication as a Success Factor",
      subchapters: [
        {
          id: "ch1.1",
          title: "1.1 Introduction to Information Systems",
          kcs: ["Data vs Information", "The value of information", "Information Systems in Organizations"],
          prerequisites: [],
        },
        {
          id: "ch1.2",
          title: "1.2 IT and Business Strategy Alignment",
          kcs: ["Strategic alignment model", "Competitive advantage through IT", "CIO Role"],
          prerequisites: ["ch1.1"],
        }
      ]
    },
    {
      id: "ch2",
      title: "2. Management of Information Systems",
      subchapters: [
        {
          id: "ch2.1",
          title: "2.1 Planning and Strategy",
          kcs: ["IT Planning process", "Enterprise Architecture", "Portfolio Management"],
          prerequisites: ["ch1.2"],
        },
        {
          id: "ch2.2",
          title: "2.2 IT Governance and Compliance",
          kcs: ["COBIT", "ITIL", "Risk Management"],
          prerequisites: ["ch2.1"],
        }
      ]
    }
  ]
};

// Simulated Merill's First Principles states (for the Learner Profile)
export const initialMerillState = {
  orientation: 'pending', // pending, active, completed
  delivery: 'pending',
  practice: 'pending',
  assessment: 'pending',
  integration: 'pending',
};
