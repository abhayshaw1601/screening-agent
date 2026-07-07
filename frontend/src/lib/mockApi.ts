export interface LogEntry {
  question: string;
  answer: string | null;
  timestamp: string;
}

export interface StartResponse {
  session_id: string;
  role: string;
  skills: string[];
  question: string;
  current_step: number;
}

export interface SubmitResponse {
  is_completed: boolean;
  next_question: string | null;
  current_step: number;
  evaluation_summary: string | null;
}

export interface SummaryResponse {
  session_id: string;
  role: string;
  skills: string[];
  status: string;
  current_step: number;
  evaluation_summary: string | null;
  logs: LogEntry[];
}

// Preset questions depending on the job role
const QUESTIONS_MOCK: Record<string, string[]> = {
  "AI/ML Engineer": [
    "What is gradient descent and how does it optimize a loss function?",
    "Can you explain the difference between Encoder-only (like BERT) and Decoder-only (like GPT) Transformer architectures?",
    "How do you handle severe class imbalance in a tabular classification dataset?",
    "What are some strategies to reduce memory footprint when training a very large deep learning model?",
    "What is Retrieval-Augmented Generation (RAG), and what are the main factors that affect its retrieval accuracy?",
  ],
  "Backend Engineer": [
    "How do you design a database schema to support scaling writes in a high-concurrency e-commerce application?",
    "Can you explain the difference between optimistic and pessimistic locking in databases?",
    "What are the advantages of FastAPI over Flask, particularly regarding asynchronous request handling?",
    "How would you implement secure token-based user authentication and session management?",
    "What is the role of a message broker like RabbitMQ or Kafka in decoupling microservices?",
  ],
  "General / Other": [
    "Tell me about a challenging technical project you worked on and how you resolved the obstacles.",
    "How do you approach writing clean, readable, and maintainable code?",
    "What is your preference between SQL and NoSQL databases, and how do you decide which to use?",
    "How do you configure CI/CD pipelines to guarantee software deployment safety?",
    "Explain the concept of REST APIs and how they differ from GraphQL/gRPC.",
  ]
};

// Simulation state database (stored in session storage for refreshing sanity)
const getSessionStorageDb = (): Record<string, SummaryResponse> => {
  if (typeof window === "undefined") return {};
  const data = sessionStorage.getItem("mock_db");
  return data ? JSON.parse(data) : {};
};

const saveSessionStorageDb = (db: Record<string, SummaryResponse>) => {
  if (typeof window === "undefined") return;
  sessionStorage.setItem("mock_db", JSON.stringify(db));
};

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const mockStartInterview = async (
  role: string,
  skills: string[]
): Promise<StartResponse> => {
  await delay(1500); // Simulate network latency

  const session_id = "mock-" + Math.random().toString(36).substr(2, 9);
  const matchedRole = QUESTIONS_MOCK[role] ? role : "General / Other";
  const question = QUESTIONS_MOCK[matchedRole][0];

  const session: SummaryResponse = {
    session_id,
    role,
    skills,
    status: "ACTIVE",
    current_step: 1,
    evaluation_summary: null,
    logs: [
      {
        question,
        answer: null,
        timestamp: new Date().toISOString()
      }
    ]
  };

  const db = getSessionStorageDb();
  db[session_id] = session;
  saveSessionStorageDb(db);

  return {
    session_id,
    role,
    skills,
    question,
    current_step: 1
  };
};

export const mockSubmitAnswer = async (
  session_id: string,
  answer: string
): Promise<SubmitResponse> => {
  await delay(1200); // Simulate model evaluation latency

  const db = getSessionStorageDb();
  const session = db[session_id];

  if (!session) {
    throw new Error("Session not found");
  }

  // Update latest answer
  const latestLog = session.logs[session.logs.length - 1];
  latestLog.answer = answer;

  const matchedRole = QUESTIONS_MOCK[session.role] ? session.role : "General / Other";
  const questionsList = QUESTIONS_MOCK[matchedRole];
  const nextStepIndex = session.logs.length; // e.g., if length is 1, next index is 1 (which is Q2)

  if (nextStepIndex >= 5) {
    // Generate Final Evaluation
    session.status = "COMPLETED";
    session.evaluation_summary = `
# Interview Evaluation Report

## 1. Overall Assessment
The candidate demonstrated a strong baseline understanding of core engineering principles relevant to **${session.role}**. Throughout the 5-step conversation, their responses showed both conceptual grasp and practical awareness of engineering compromises.

## 2. Strengths
- **Structured Explanations**: Clear explanation of concepts and architectural trade-offs.
- **Applied Contextual Knowledge**: Referenced specific technologies (${session.skills.slice(0, 4).join(", ")}) during scenario-based discussions.
- **Logical Flow**: Maintained consistent rationale across all questions.

## 3. Areas for Improvement
- Deepen understanding of low-level optimization and latency tuning.
- Could provide more specific examples of dealing with failure recovery and operational metrics.

## 4. Final Recommendation
- **Recommended Status**: **Pass (Advance to System Design Round)**
- **Technical Score**: **8.5 / 10**
    `.trim();

    db[session_id] = session;
    saveSessionStorageDb(db);

    return {
      is_completed: true,
      next_question: null,
      current_step: 5,
      evaluation_summary: session.evaluation_summary
    };
  }

  // Next Question
  const nextQuestion = questionsList[nextStepIndex];
  session.logs.push({
    question: nextQuestion,
    answer: null,
    timestamp: new Date().toISOString()
  });
  session.current_step = nextStepIndex + 1;

  db[session_id] = session;
  saveSessionStorageDb(db);

  return {
    is_completed: false,
    next_question: nextQuestion,
    current_step: session.current_step,
    evaluation_summary: null
  };
};

export const mockGetSummary = async (session_id: string): Promise<SummaryResponse> => {
  await delay(600);
  const db = getSessionStorageDb();
  const session = db[session_id];

  if (!session) {
    throw new Error("Session not found");
  }

  return session;
};
