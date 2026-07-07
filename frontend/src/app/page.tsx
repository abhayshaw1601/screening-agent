"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Upload,
  ChevronRight,
  MessageSquare,
  Award,
  Clock,
  ArrowRight,
  RefreshCw,
  Send,
  CheckCircle,
  FileText,
  Brain,
  User,
  Sparkles,
  ChevronDown,
  X as XIcon,
  ArrowUp
} from "lucide-react";
import { LogEntry } from "../lib/mockApi";
import { Spinner } from "../components/ui/spinner";
import {
  Attachment,
  AttachmentAction,
  AttachmentActions,
  AttachmentContent,
  AttachmentDescription,
  AttachmentGroup,
  AttachmentMedia,
  AttachmentTitle,
} from "../components/ui/attachment";
import { motion, AnimatePresence } from "framer-motion";

function parseInlineMarkdown(text: string): React.ReactNode[] | string {
  const parts: React.ReactNode[] = [];
  const regex = /(\*\*|__)(.*?)\1|(\*|_)(.*?)\3/g;
  let match;
  let lastIndex = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    if (match[1]) {
      parts.push(
        <strong className="font-bold text-white" key={match.index}>
          {match[2]}
        </strong>
      );
    } else if (match[3]) {
      parts.push(
        <em className="italic text-white/90" key={match.index}>
          {match[4]}
        </em>
      );
    }

    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length > 0 ? parts : text;
}

function renderMarkdown(text: string): React.ReactNode {
  if (!text) return null;

  const lines = text.split("\n");

  return (
    <div className="text-left font-sans">
      {lines.map((line, idx) => {
        // #### H4
        if (line.startsWith("#### ")) {
          return (
            <h4 key={idx} className="text-[11px] font-semibold text-white/90 mt-4 mb-1.5 font-mono tracking-wide">
              {parseInlineMarkdown(line.slice(5))}
            </h4>
          );
        }
        // ### H3
        if (line.startsWith("### ")) {
          return (
            <h3 key={idx} className="text-xs font-bold text-white mt-5 mb-2 font-mono uppercase tracking-wide">
              {parseInlineMarkdown(line.slice(4))}
            </h3>
          );
        }
        // ## H2
        if (line.startsWith("## ")) {
          return (
            <h2 key={idx} className="text-sm font-semibold text-white mt-5 mb-2 font-mono uppercase tracking-wide border-b border-white/10 pb-2">
              {parseInlineMarkdown(line.slice(3))}
            </h2>
          );
        }
        // # H1
        if (line.startsWith("# ")) {
          return (
            <h1 key={idx} className="text-base font-bold text-white mt-6 mb-3 font-mono border-b border-white/10 pb-2 uppercase tracking-wide">
              {parseInlineMarkdown(line.slice(2))}
            </h1>
          );
        }
        // Horizontal rule
        if (/^-{3,}$/.test(line.trim()) || /^\*{3,}$/.test(line.trim())) {
          return <hr key={idx} className="border-white/10 my-4" />;
        }
        // Numbered list (e.g. "1. ", "2. ")
        if (/^\d+\.\s/.test(line.trim())) {
          const content = line.trim().replace(/^\d+\.\s/, "");
          return (
            <li key={idx} className="list-decimal list-inside text-xs text-white/80 ml-4 mb-1.5 leading-relaxed">
              {parseInlineMarkdown(content)}
            </li>
          );
        }
        // Bullet list
        if (line.trim().startsWith("- ") || line.trim().startsWith("* ")) {
          const content = line.trim().slice(2);
          return (
            <li key={idx} className="list-disc list-inside text-xs text-white/80 ml-4 mb-1.5 leading-relaxed">
              {parseInlineMarkdown(content)}
            </li>
          );
        }
        // Empty line
        if (!line.trim()) {
          return <div key={idx} className="h-1.5" />;
        }
        // Default paragraph
        return (
          <p key={idx} className="text-xs text-white/80 mb-2 leading-relaxed font-sans">
            {parseInlineMarkdown(line)}
          </p>
        );
      })}
    </div>
  );
}

function calculateMetrics(summary: string, logs: LogEntry[]) {
  console.log("=== CALCULATING METRICS FOR EVALUATION SUMMARY ===");
  console.log("Summary Text:", summary);
  
  let rawScore = 8.0;
  if (summary) {
    const scoreRegex = /(?:score|rating)\D*(\d+(?:\.\d+)?)\s*\/\s*10/i;
    const match = summary.match(scoreRegex);
    if (match && match[1]) {
      const val = parseFloat(match[1]);
      if (!isNaN(val) && val >= 0 && val <= 10) {
        rawScore = val;
      }
    } else {
      const simpleRegex = /(\d+(?:\.\d+)?)\s*\/\s*10/;
      const simpleMatch = summary.match(simpleRegex);
      if (simpleMatch && simpleMatch[1]) {
        const val = parseFloat(simpleMatch[1]);
        if (!isNaN(val) && val >= 0 && val <= 10) {
          rawScore = val;
        }
      }
    }
  }
  
  console.log(">>> EXTRACTED RAW SCORE:", rawScore);

  const techDepth = Math.round(rawScore * 10);

  let totalChars = 0;
  let answerCount = 0;
  logs.forEach((log) => {
    if (log.answer) {
      totalChars += log.answer.length;
      answerCount++;
    }
  });
  const avgLength = answerCount > 0 ? totalChars / answerCount : 0;
  let commScore = 75;
  if (avgLength > 200) commScore = 95;
  else if (avgLength > 100) commScore = 88;
  else if (avgLength > 50) commScore = 78;
  else if (avgLength > 0) commScore = 65;

  const completeness = Math.min(100, Math.round((logs.length / 5) * 100));

  return {
    techDepth: `${techDepth}%`,
    communication: `${commScore}%`,
    completeness: `${completeness}%`
  };
}

type ScreenState = "WELCOME" | "CHAT" | "INSIGHTS";

export default function WorkspacePage() {
  // Screen and UI flow states
  const [screen, setScreen] = useState<ScreenState>("WELCOME");

  // Welcome screen states
  const [selectedRole, setSelectedRole] = useState<string>("AI/ML Engineer");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessingPdf, setIsProcessingPdf] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Session / Chat states
  const [sessionId, setSessionId] = useState<string>("");
  const [skills, setSkills] = useState<string[]>([]);
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [chatLog, setChatLog] = useState<Array<{ sender: "AI" | "USER"; text: string; timestamp: Date }>>([]);
  const [currentAnswer, setCurrentAnswer] = useState<string>("");
  const [isWaitingForAi, setIsWaitingForAi] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Performance / Summary states
  const [evaluationSummary, setEvaluationSummary] = useState<string>("");
  const [historicalLogs, setHistoricalLogs] = useState<LogEntry[]>([]);

  // System validation alerts
  const [welcomeError, setWelcomeError] = useState<string>(" ");

  // Scrolling & input activation elements
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Auto-scroll chat view to bottom on messages update
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatLog, isWaitingForAi]);

  // Auto-focus/activate response input field when AI completes question generation
  useEffect(() => {
    if (!isWaitingForAi && screen === "CHAT") {
      inputRef.current?.focus();
    }
  }, [isWaitingForAi, screen]);

  // ---------------------------------------------------------------------------
  // HANDLERS: Welcome / Ingestion Screen
  // ---------------------------------------------------------------------------

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const processSelectedFile = (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setWelcomeError("Only PDF resumes are supported at this stage.");
      setResumeFile(null);
      return;
    }
    setWelcomeError("");
    setResumeFile(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processSelectedFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processSelectedFile(e.target.files[0]);
    }
  };

  const handleStartInterview = async () => {
    if (!resumeFile) {
      setWelcomeError("Please upload a PDF resume to start the screening.");
      return;
    }

    setIsProcessingPdf(true);
    setWelcomeError("");

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "";
      const formData = new FormData();
      formData.append("role", selectedRole);
      formData.append("file", resumeFile);

      const response = await fetch(`${apiBase}/api/interview/start`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to initialize interview session.");
      }

      const res = await response.json();

      setSessionId(res.session_id);
      setSkills(res.skills);
      setCurrentStep(res.current_step);
      setChatLog([
        {
          sender: "AI",
          text: res.question,
          timestamp: new Date()
        }
      ]);

      setScreen("CHAT");
    } catch (err: any) {
      setWelcomeError(err.message || "Failed to initialize interview session. Ensure the backend is active.");
    } finally {
      setIsProcessingPdf(false);
    }
  };

  // ---------------------------------------------------------------------------
  // HANDLERS: Chat Interface
  // ---------------------------------------------------------------------------

  const handleSubmitAnswer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentAnswer.trim() || isSubmitting) return;

    const answerToSubmit = currentAnswer.trim();
    setCurrentAnswer("");
    setIsSubmitting(true);
    setIsWaitingForAi(true);

    const isFinalStep = currentStep === 5;
    if (isFinalStep) {
      setScreen("INSIGHTS");
    }

    // Add candidate's message locally
    setChatLog((prev) => [
      ...prev,
      {
        sender: "USER",
        text: answerToSubmit,
        timestamp: new Date()
      }
    ]);

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "";
      const response = await fetch(`${apiBase}/api/interview/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, answer: answerToSubmit }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to submit answer.");
      }

      const res = await response.json();

      if (res.is_completed) {
        // Transition to INSIGHTS immediately so the skeleton dashboard is shown
        setScreen("INSIGHTS");

        // Fetch full summary to present historical transcripts side-by-side
        const summaryRes = await fetch(`${apiBase}/api/interview/summary/${sessionId}`);
        if (!summaryRes.ok) {
          throw new Error("Failed to load completed session summary.");
        }
        const summary = await summaryRes.json();
        setEvaluationSummary(summary.evaluation_summary || "");

        // Convert timestamp strings from backend schema back to Date objects in the frontend logs
        const formattedLogs = (summary.logs || []).map((log: any) => ({
          ...log,
          timestamp: log.timestamp ? new Date(log.timestamp) : null
        }));

        setHistoricalLogs(formattedLogs);
      } else {
        setCurrentStep(res.current_step);
        // Append AI question to chat log
        setChatLog((prev) => [
          ...prev,
          {
            sender: "AI",
            text: res.next_question || "",
            timestamp: new Date()
          }
        ]);
      }
    } catch (err: any) {
      // Revert screen to CHAT so the user can see the error in the chat log
      setScreen("CHAT");
      setChatLog((prev) => [
        ...prev,
        {
          sender: "AI",
          text: `[SYSTEM ERROR]: ${err.message || "Failed to communicate with screening engine."}`,
          timestamp: new Date()
        }
      ]);
    } finally {
      setIsSubmitting(false);
      setIsWaitingForAi(false);
    }
  };

  // ---------------------------------------------------------------------------
  // HANDLERS: General / Restart
  // ---------------------------------------------------------------------------

  const handleRestart = () => {
    setScreen("WELCOME");
    setResumeFile(null);
    setWelcomeError("");
    setChatLog([]);
    setEvaluationSummary("");
    setHistoricalLogs([]);
    setCurrentAnswer("");
  };

  return (
    <main className="relative overflow-hidden flex flex-col min-h-screen items-center justify-center p-4 md:p-8 bg-[#090A0F] text-[#F8FAFC]">

      {/* Background gradient image */}
      <div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat pointer-events-none opacity-40 z-0"
        style={{ backgroundImage: "url('https://writemate.demos.tailgrids.com/images/Gradient.png')" }}
      />

      {/* Header Bar - WriteMate Style */}
      <header className="w-full max-w-5xl flex items-center justify-between mb-12 pb-5 border-b border-white/10 z-10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 flex items-center justify-center bg-white text-black font-bold text-lg rounded-md tracking-tight select-none">
            AGI
          </div>
          <div>
            <h1 className="font-bold text-sm tracking-tight text-white uppercase font-mono">
              Screener
            </h1>
            <p className="text-[10px] text-white/50 font-mono tracking-widest uppercase">System Evaluation</p>
          </div>
        </div>

        {screen !== "WELCOME" && (
          <button
            onClick={handleRestart}
            className="flex items-center gap-2 px-4 py-2 border border-white/20 bg-white/5 rounded-md text-xs font-mono font-medium text-white/80 hover:text-white hover:bg-white/10 hover:border-white/30 transition-all duration-300"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Reset Session
          </button>
        )}
      </header>

      {/* AnimatePresence for transitions between phases */}
      <AnimatePresence mode="wait">

        {/* VIEW A: Welcome / Ingestion setup */}
        {screen === "WELCOME" && (
          <motion.section
            key="welcome"
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -15 }}
            transition={{ type: "spring", stiffness: 260, damping: 25 }}
            className="w-full max-w-5xl z-10"
          >
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">

              {/* Left Column: Heading and features */}
              <div className="lg:col-span-7 text-left space-y-6">
                {/* <div className="flex items-center gap-2 text-white/80">
                  <span className="text-[10px] font-mono tracking-wider uppercase bg-white/10 px-2.5 py-1 rounded border border-white/5">
                    Phase 4 Verification
                  </span>
                </div> */}
                <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight text-white leading-tight font-sans">
                  Screen Better. <br />
                  Interview Faster. <br />
                  Verify with AI.
                </h2>
                <p className="text-xs text-white/50 leading-relaxed font-sans max-w-md">
                  Your all-in-one candidate screening engine. Upload technical resumes, parse qualifications, and conduct textbook-grounded interactive assessments instantly.
                </p>
                <div className="space-y-3 pt-2">
                  {[
                    "Grounded Textbook Reference RAG",
                    "State-Driven Adaptive Agentic Loop",
                    "Zero-Dependency PDF Resume Extraction",
                    "Automated Performance Grading Reports"
                  ].map((feat) => (
                    <div key={feat} className="flex items-center gap-2.5 text-xs text-white/70 font-mono">
                      <span className="text-white font-bold select-none">[v]</span>
                      {feat}
                    </div>
                  ))}
                </div>
              </div>

              {/* Right Column: Ingestion Card Box */}
              <div className="lg:col-span-5 bg-white/[0.03] border border-white/10 p-6 md:p-8 rounded-xl space-y-6">

                {/* Job Role Dropdown */}
                <div className="flex flex-col gap-2">
                  <label className="text-[10px] font-mono uppercase tracking-wider text-white/40">Target Role</label>
                  <div className="relative">
                    <select
                      value={selectedRole}
                      onChange={(e) => setSelectedRole(e.target.value)}
                      className="w-full bg-[#111218] border border-white/10 rounded-md px-4 py-3 text-xs font-mono text-white outline-none focus:border-white/30 transition-all appearance-none cursor-pointer"
                    >
                      <option value="AI/ML Engineer">AI/ML Engineer</option>
                      <option value="Frontend Engineer">Frontend Engineer</option>
                      <option value="Backend Engineer">Backend Engineer</option>
                      <option value="Full Stack Engineer">Full Stack Engineer</option>
                      <option value="DevOps Engineer">DevOps Engineer</option>
                      <option value="General / Other">General / Other</option>
                    </select>
                    <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-white/40">
                      <ChevronDown className="w-4 h-4" />
                    </div>
                  </div>
                </div>

                {/* Custom File Upload Dropzone */}
                <div className="flex flex-col gap-2">
                  <label className="text-[10px] font-mono uppercase tracking-wider text-white/40">Upload PDF Resume</label>

                  {isProcessingPdf ? (
                    /* Rectangular uploading card */
                    <Attachment state="uploading" className="w-full bg-white/[0.02] border-white/10 rounded-md">
                      <AttachmentMedia>
                        <Spinner className="text-white" />
                      </AttachmentMedia>
                      <AttachmentContent>
                        <AttachmentTitle className="font-mono text-white/80">{resumeFile?.name || "resume.pdf"}</AttachmentTitle>
                        <AttachmentDescription className="font-mono text-white/40">
                          Uploading & Parsing PDF Structure...
                        </AttachmentDescription>
                      </AttachmentContent>
                    </Attachment>
                  ) : resumeFile ? (
                    /* Square loaded card after upload */
                    <AttachmentGroup className="justify-center py-6 bg-white/[0.01] border border-white/5 rounded-md">
                      <Attachment orientation="vertical" className="relative group bg-white/[0.03] border-white/10 w-36 h-auto flex flex-col flex-nowrap p-4 gap-3 rounded-md">
                        <AttachmentMedia variant="image" className="w-full aspect-square bg-[#111218] border-white/10">
                          <div className="flex flex-col items-center justify-center h-full w-full bg-[#090A0F] text-white/60">
                            <FileText className="w-8 h-8" />
                          </div>
                        </AttachmentMedia>
                        <AttachmentContent className="mt-1">
                          <AttachmentTitle className="text-center text-[11px] font-mono text-white block truncate max-w-full">
                            {resumeFile.name}
                          </AttachmentTitle>
                          <AttachmentDescription className="text-center text-[9px] font-mono text-white/40 block mt-1 truncate max-w-full">
                            {(resumeFile.size / 1024).toFixed(1)} KB - PDF
                          </AttachmentDescription>
                        </AttachmentContent>
                        <AttachmentActions className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                          <AttachmentAction
                            onClick={(e) => {
                              e.stopPropagation();
                              setResumeFile(null);
                            }}
                            className="bg-[#090A0F] border border-white/10 text-white/60 hover:text-white rounded-md p-1"
                            aria-label="Remove resume"
                          >
                            <XIcon className="w-3.5 h-3.5" />
                          </AttachmentAction>
                        </AttachmentActions>
                      </Attachment>
                    </AttachmentGroup>
                  ) : (
                    /* Clickable Drag & Drop Zone */
                    <div
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}
                      onClick={() => fileInputRef.current?.click()}
                      className={`flex flex-col items-center justify-center border-2 border-dashed rounded-md p-8 cursor-pointer transition-all duration-300 ${isDragging
                        ? "border-white bg-white/5 scale-[0.99]"
                        : "border-white/10 bg-white/[0.02] hover:border-white/30 hover:bg-white/[0.04]"
                        }`}
                    >
                      <input
                        type="file"
                        ref={fileInputRef}
                        onChange={handleFileChange}
                        accept=".pdf"
                        className="hidden"
                      />
                      <div className="flex flex-col items-center text-center">
                        <div className="p-3 bg-white/5 text-white/60 rounded-md border border-white/10 mb-4">
                          <Upload className="w-6 h-6" />
                        </div>
                        <p className="text-xs font-mono font-semibold text-white/80">Drag & drop your PDF resume here</p>
                        <p className="text-[10px] font-mono text-white/40 mt-2">
                          or click to browse local files (PDF only, max 5MB)
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Error alerts */}
                {/* {welcomeError && (
                  <div className="p-3.5 rounded-md bg-white/5 border border-white/10 text-[11px] font-mono text-white flex items-center gap-2">
                    <span className="w-1.5 h-1.5 bg-white rounded-full animate-ping" />
                    {welcomeError}
                  </div>
                )} */}

                {/* Submit CTA - Solid White like WriteMate */}
                <button
                  onClick={handleStartInterview}
                  disabled={isProcessingPdf || !resumeFile}
                  className={`w-full py-3.5 px-4 rounded-md font-mono text-xs tracking-tight flex items-center justify-center gap-2 border transition-all duration-300 ${isProcessingPdf || !resumeFile
                    ? "bg-white/5 text-white/20 border-white/5 cursor-not-allowed"
                    : "bg-white text-black font-bold border-white hover:bg-white/90"
                    }`}
                >
                  {isProcessingPdf ? (
                    <>
                      <Spinner className="w-4 h-4 mr-1 text-black" />
                      Initializing Assessment...
                    </>
                  ) : (
                    <>
                      Start Technical Assessment
                      <ArrowRight className="w-3.5 h-3.5" />
                    </>
                  )}
                </button>
              </div>

            </div>
          </motion.section>
        )}

        {/* VIEW B: Interactive Screening Chat Panel */}
        {screen === "CHAT" && (
          <motion.section
            key="chat"
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -15 }}
            transition={{ type: "spring", stiffness: 260, damping: 25 }}
            className="w-full max-w-4xl flex flex-col h-[75vh] bg-white/[0.02] border border-white/10 rounded-xl z-10"
          >
            {/* Interview Header Info */}
            <div className="px-6 py-4 border-b border-white/10 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white/[0.01] rounded-t-xl">
              <div className="flex items-center gap-3">
                {/* <div className="w-2 h-2 bg-white rounded-full animate-ping" /> */}
                <div>
                  <h3 className="font-bold text-xs font-mono text-white uppercase">{selectedRole} Session</h3>
                  <p className="text-[10px] font-mono text-white/40 mt-1">
                    Skills: {skills.slice(0, 5).join(", ")}
                  </p>
                </div>
              </div>

              {/* Step counter and progress track */}
              <div className="flex flex-col items-end gap-2">
                <div className="px-2.5 py-1 bg-white/5 border border-white/10 rounded text-[10px] font-mono text-white flex items-center gap-1.5">
                  <Clock className="w-3 h-3 text-white/60" />
                  Step {currentStep} of 5
                </div>
                <div className="w-28 h-1 bg-white/10 rounded-full overflow-hidden">
                  <motion.div
                    layout
                    className="h-full bg-white"
                    initial={{ width: "0%" }}
                    animate={{ width: `${(currentStep / 5) * 100}%` }}
                    transition={{ type: "spring", stiffness: 260, damping: 25 }}
                  />
                </div>
              </div>
            </div>

            {/* Conversation Bubbles */}
            <div className="flex-1 p-6 overflow-y-auto space-y-6">
              {chatLog.map((msg, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, y: 10, scale: 0.97 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ type: "spring", stiffness: 300, damping: 28 }}
                  className={`flex gap-3 max-w-[85%] ${msg.sender === "USER" ? "ml-auto flex-row-reverse" : "mr-auto"
                    }`}
                >
                  {/* Avatar Icon */}
                  <div
                    className={`w-8 h-8 rounded flex items-center justify-center border flex-shrink-0 ${msg.sender === "USER"
                      ? "bg-white border-white text-black"
                      : "bg-white/5 border-white/10 text-white"
                      }`}
                  >
                    {msg.sender === "USER" ? <User className="w-3.5 h-3.5" /> : <Brain className="w-3.5 h-3.5" />}
                  </div>

                  {/* Bubble content */}
                  <div>
                    <div
                      className={`p-4 rounded-lg text-xs leading-relaxed ${msg.sender === "USER"
                        ? "bg-white text-black font-sans"
                        : "bg-white/5 text-white/90 border border-white/10 font-sans"
                        }`}
                    >
                      {msg.text}
                    </div>
                    <span className="text-[9px] font-mono text-white/30 block mt-1.5 px-1">
                      {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </motion.div>
              ))}

              {/* AI Processing Skeleton / Indicator */}
              {isWaitingForAi && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex gap-3 max-w-[85%] mr-auto"
                >
                  <div className="w-8 h-8 rounded flex items-center justify-center bg-white/5 border border-white/10 text-white">
                    <Brain className="w-3.5 h-3.5 animate-pulse" />
                  </div>
                  <div className="bg-white/5 border border-white/10 p-4 rounded-lg space-y-2.5 w-48">
                    <div className="h-2 bg-white/20 rounded w-5/6 animate-pulse" />
                    <div className="h-2 bg-white/20 rounded w-1/2 animate-pulse" />
                  </div>
                </motion.div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Form input - Styled exactly like WriteMate Prompt Bar */}
            <form
              onSubmit={handleSubmitAnswer}
              className="p-4 border-t border-white/10 bg-[#090A0F]/60 rounded-b-xl"
            >
              <div className="relative flex items-center bg-black border border-white/20 rounded-none focus-within:border-white transition-all duration-300">
                <input
                  ref={inputRef}
                  type="text"
                  value={currentAnswer}
                  onChange={(e) => setCurrentAnswer(e.target.value)}
                  placeholder="Write response here..."
                  disabled={isSubmitting}
                  className="w-full bg-transparent px-5 py-4 pr-16 text-xs text-white placeholder-white/35 outline-none font-sans"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleSubmitAnswer(e);
                    }
                  }}
                />
                <button
                  type="submit"
                  disabled={!currentAnswer.trim() || isSubmitting}
                  className={`absolute right-0 top-0 bottom-0 aspect-square flex items-center justify-center rounded-none transition-all duration-300 ${currentAnswer.trim() && !isSubmitting
                    ? "bg-white text-black hover:bg-white/90 cursor-pointer"
                    : "bg-white/10 text-white/20 cursor-not-allowed"
                    }`}
                >
                  <ArrowUp className="w-4 h-4" />
                </button>
              </div>
              <p className="text-[9px] font-mono text-white/30 mt-2 px-1 text-center md:text-left">
                Instruction: Press [Enter] to submit message response.
              </p>
            </form>
          </motion.section>
        )}

        {/* VIEW C: Performance Insights Screen */}
        {screen === "INSIGHTS" && (
          <motion.section
            key="insights"
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -15 }}
            transition={{ type: "spring", stiffness: 260, damping: 25 }}
            className="w-full max-w-5xl grid grid-cols-1 lg:grid-cols-3 gap-6 z-10"
          >

            {!evaluationSummary ? (
              /* High-Premium Pulsing Skeleton Report Layout */
              <>
                {/* Column A: Evaluation Report Skeleton */}
                <div className="lg:col-span-2 space-y-6">
                  <div className="bg-white/[0.02] border border-white/10 p-6 md:p-8 rounded-xl">
                    <div className="flex items-center gap-2 text-white/40 mb-4 animate-pulse">
                      <Award className="w-4.5 h-4.5" />
                      <div className="h-2.5 bg-white/20 rounded w-28" />
                    </div>
                    <div className="h-5 bg-white/10 rounded w-1/3 mb-8 animate-pulse" />

                    {/* 3 Performance metrics skeleton cards */}
                    <div className="grid grid-cols-3 gap-4 mb-8">
                      {[1, 2, 3].map((i) => (
                        <div
                          key={i}
                          className="p-4 bg-[#111218] border border-white/5 rounded-md space-y-3 animate-pulse"
                        >
                          <div className="h-2 bg-white/20 rounded w-2/3" />
                          <div className="h-5 bg-white/10 rounded w-1/2" />
                          <div className="h-2 bg-white/20 rounded w-3/4" />
                        </div>
                      ))}
                    </div>

                    {/* Performance description skeleton lines */}
                    <div className="border-t border-white/10 pt-6 space-y-4 animate-pulse">
                      <div className="h-2.5 bg-white/20 rounded w-1/4 mb-3" />
                      <div className="h-3 bg-white/10 rounded w-full" />
                      <div className="h-3 bg-white/10 rounded w-11/12" />
                      <div className="h-3 bg-white/10 rounded w-5/6" />
                      <div className="h-3 bg-white/10 rounded w-full" />
                      <div className="h-3 bg-white/10 rounded w-3/4" />
                      
                      <div className="h-2.5 bg-white/20 rounded w-1/5 mt-6 mb-3" />
                      <div className="h-3 bg-white/10 rounded w-full" />
                      <div className="h-3 bg-white/10 rounded w-5/6" />
                      <div className="h-3 bg-white/10 rounded w-11/12" />
                    </div>
                  </div>
                </div>

                {/* Column B: Transcript Tree Skeleton */}
                <div className="lg:col-span-1 space-y-6">
                  <div className="bg-white/[0.02] border border-white/10 p-6 rounded-xl flex flex-col h-[70vh] justify-between">
                    <div className="space-y-5 flex-1 overflow-hidden">
                      <div className="flex items-center gap-2 text-white/40 mb-5 animate-pulse">
                        <MessageSquare className="w-4 h-4" />
                        <div className="h-2.5 bg-white/20 rounded w-36" />
                      </div>

                      {/* Pulse cards */}
                      <div className="space-y-4 pr-1 animate-pulse">
                        {[1, 2, 3].map((i) => (
                          <div key={i} className="p-4 bg-[#111218] border border-white/5 rounded-md space-y-3">
                            <div className="flex items-center gap-2">
                              <div className="w-6 h-4 bg-white/20 rounded" />
                              <div className="h-2 bg-white/10 rounded w-3/4" />
                            </div>
                            <div className="flex items-center gap-2 border-t border-white/5 pt-2.5">
                              <div className="w-6 h-4 bg-white/10 rounded" />
                              <div className="h-2 bg-white/5 rounded w-1/2" />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Recruiter waiting status indicators */}
                    <div className="mt-5 p-4 bg-white/5 border border-white/10 rounded-md flex items-center justify-center gap-3">
                      <Spinner className="text-white" />
                      <span className="text-[11px] font-mono text-white/60 animate-pulse uppercase tracking-wider">Generating evaluation...</span>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <>
                {/* Column A: Evaluation Report */}
                <div className="lg:col-span-2 space-y-6">
                  <div className="bg-white/[0.02] border border-white/10 p-6 md:p-8 rounded-xl">
                    <div className="flex items-center gap-2 text-white/60 mb-4">
                      <Award className="w-4.5 h-4.5" />
                      <span className="text-[10px] font-mono uppercase tracking-wider">Evaluation Report</span>
                    </div>
                    <h2 className="text-lg md:text-xl font-bold mb-8 text-white uppercase font-mono tracking-tight">Performance Summary</h2>

                    {/* 3 Performance metrics cards with staggered reveal */}
                    <div className="grid grid-cols-3 gap-4 mb-8">
                      {(() => {
                        const metrics = calculateMetrics(evaluationSummary, historicalLogs);
                        return [
                          { title: "Technical Depth", score: metrics.techDepth, label: "Textbook Grounded" },
                          { title: "Communication", score: metrics.communication, label: "Syntactic Layout" },
                          { title: "Completeness", score: metrics.completeness, label: "Turn Limit Met" },
                        ].map((metric, i) => (
                          <motion.div
                            key={metric.title}
                            initial={{ opacity: 0, y: 15 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{
                              type: "spring",
                              stiffness: 260,
                              damping: 25,
                              delay: i * 0.05,
                            }}
                            className="p-4 bg-[#111218] border border-white/10 rounded-md"
                          >
                            <span className="text-[9px] font-mono uppercase text-white/40 tracking-wider">
                              {metric.title}
                            </span>
                            <div className="text-lg font-bold text-white font-mono mt-1">
                              {metric.score}
                            </div>
                            <div className="text-[9px] font-mono text-white/30 mt-1">
                              {metric.label}
                            </div>
                          </motion.div>
                        ));
                      })()}
                    </div>

                    {/* Performance description */}
                    <div className="prose prose-invert max-w-none text-xs text-white/80 leading-relaxed border-t border-white/10 pt-6">
                      {renderMarkdown(evaluationSummary)}
                    </div>
                  </div>
                </div>

                {/* Column B: Transcript Tree */}
                <div className="lg:col-span-1 space-y-6">
                  <div className="bg-white/[0.02] border border-white/10 p-6 rounded-xl flex flex-col max-h-[80vh] overflow-hidden">
                    <div className="flex items-center gap-2 text-white/60 mb-5 flex-shrink-0">
                      <MessageSquare className="w-4 h-4" />
                      <span className="text-[10px] font-mono uppercase tracking-wider">Q&A Transcript Tree</span>
                    </div>

                    {/* Scrollable list */}
                    <div className="flex-1 overflow-y-auto space-y-4 pr-1">
                      {historicalLogs.map((log, index) => (
                        <div key={index} className="p-4 bg-[#111218] border border-white/10 rounded-md space-y-3">
                          <div className="flex items-start gap-2">
                            <span className="text-[9px] font-mono font-bold px-2 py-0.5 bg-white text-black rounded border border-white/5">
                              Q{index + 1}
                            </span>
                            <p className="text-xs font-semibold text-white/90 leading-normal font-sans">{log.question}</p>
                          </div>

                          <div className="flex items-start gap-2 border-t border-white/5 pt-2.5">
                            <span className="text-[9px] font-mono font-bold px-2 py-0.5 bg-white/10 text-white/40 rounded border border-white/5">
                              A{index + 1}
                            </span>
                            <p className="text-xs text-white/50 leading-relaxed italic font-sans">
                              &ldquo;{log.answer || "(no response registered)"}&rdquo;
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Action - Solid white card */}
                    <button
                      onClick={handleRestart}
                      className="w-full mt-5 py-3.5 bg-white hover:bg-white/90 text-black rounded-md text-xs font-mono font-bold flex items-center justify-center gap-2 transition-all duration-300 flex-shrink-0"
                    >
                      Start New Session
                      <ArrowRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </>
            )}
          </motion.section>
        )}
      </AnimatePresence>

      {/* Footer copyright */}
      <footer className="w-full max-w-5xl text-center text-[9px] font-mono text-white/30 mt-16 py-5 border-t border-white/10 z-10 uppercase tracking-widest">
        [ 2026 PG AGI Screening System. Configured with High-Contrast Monospace Accents ]
      </footer>
    </main>
  );
}
