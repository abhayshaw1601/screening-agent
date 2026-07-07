"use client";

import React, { useState, useRef } from "react";
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
  ChevronDown
} from "lucide-react";
import {
  mockStartInterview,
  mockSubmitAnswer,
  mockGetSummary,
  LogEntry
} from "../lib/mockApi";

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
  const [welcomeError, setWelcomeError] = useState<string>("");

  // ═══════════════════════════════════════════════════════════════════════════
  // HANDLERS: Welcome / Upload Screen
  // ═══════════════════════════════════════════════════════════════════════════

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
      // Simulate parsing of resume and extracting mock skills
      const extractedMockSkills = selectedRole === "AI/ML Engineer"
        ? ["Python", "PyTorch", "Transformers", "SQL", "LLM", "RAG"]
        : ["FastAPI", "Python", "SQL", "Docker", "REST", "Git"];

      // Trigger Start API
      const res = await mockStartInterview(selectedRole, extractedMockSkills);
      
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
      setWelcomeError("Failed to initialize interview session. Please try again.");
    } finally {
      setIsProcessingPdf(false);
    }
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // HANDLERS: Chat Interface
  // ═══════════════════════════════════════════════════════════════════════════

  const handleSubmitAnswer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentAnswer.trim() || isSubmitting) return;

    const answerToSubmit = currentAnswer.trim();
    setCurrentAnswer("");
    setIsSubmitting(true);
    setIsWaitingForAi(true);

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
      const res = await mockSubmitAnswer(sessionId, answerToSubmit);

      if (res.is_completed) {
        // Fetch full summary to present historical transcripts side-by-side
        const summary = await mockGetSummary(sessionId);
        setEvaluationSummary(summary.evaluation_summary || "");
        setHistoricalLogs(summary.logs);
        setScreen("INSIGHTS");
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
    } catch (err) {
      console.error(err);
    } finally {
      setIsSubmitting(false);
      setIsWaitingForAi(false);
    }
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // HANDLERS: General / Restart
  // ═══════════════════════════════════════════════════════════════════════════

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
    <main className="flex flex-col min-h-screen items-center justify-center p-4 md:p-8 bg-[#0b0f19] text-[#f8fafc]">
      
      {/* Background radial glow */}
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-sky-500/10 rounded-full blur-[100px] pointer-events-none" />

      {/* Header Bar */}
      <header className="w-full max-w-5xl flex items-center justify-between mb-8 pb-4 border-b border-slate-800 z-10">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-blue-600/20 text-blue-400 rounded-xl border border-blue-500/20 glow-blue">
            <Brain className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <h1 className="font-bold text-lg tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
              AGI Screener
            </h1>
            <p className="text-xs text-slate-400">Technical Interview Engine</p>
          </div>
        </div>

        {screen !== "WELCOME" && (
          <button
            onClick={handleRestart}
            className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/80 border border-slate-700/60 rounded-lg text-xs font-medium text-slate-300 hover:text-white hover:border-slate-500 transition-all"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Reset Session
          </button>
        )}
      </header>

      {/* ═════════════════════════════════════════════════════════════════════
          VIEW A: Welcome / Ingestion setup
          ═════════════════════════════════════════════════════════════════════ */}
      {screen === "WELCOME" && (
        <section className="w-full max-w-xl glass p-6 md:p-8 rounded-2xl glow-blue z-10 animate-fade-in">
          <div className="flex items-center gap-2 text-blue-400 mb-2">
            <Sparkles className="w-4 h-4" />
            <span className="text-xs font-bold uppercase tracking-wider">Phase 4 — Verification Sandbox</span>
          </div>
          <h2 className="text-2xl md:text-3xl font-extrabold mb-4 bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
            Technical Screening Sandbox
          </h2>
          <p className="text-sm text-slate-300 mb-6 leading-relaxed">
            Welcome to the candidate evaluation workspace. Select the target position and upload a professional resume in PDF format to initialize the automated screening process.
          </p>

          <div className="space-y-5">
            {/* Job Role Dropdown */}
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-400">Target Role</label>
              <div className="relative">
                <select
                  value={selectedRole}
                  onChange={(e) => setSelectedRole(e.target.value)}
                  className="w-full bg-[#0f172a] border border-slate-700/80 rounded-xl px-4 py-3 text-sm font-medium text-slate-200 outline-none focus:border-blue-500 transition-colors appearance-none cursor-pointer"
                >
                  <option value="AI/ML Engineer">AI/ML Engineer</option>
                  <option value="Backend Engineer">Backend Engineer</option>
                  <option value="General / Other">General / Other</option>
                </select>
                <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-slate-400">
                  <ChevronDown className="w-4 h-4" />
                </div>
              </div>
            </div>

            {/* Custom File Upload Dropzone */}
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-400">Upload PDF Resume</label>
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`flex flex-col items-center justify-center border-2 border-dashed rounded-2xl p-6 md:p-8 cursor-pointer transition-all duration-300 ${
                  isDragging
                    ? "border-blue-500 bg-blue-500/10 scale-[0.99]"
                    : resumeFile
                    ? "border-emerald-500/50 bg-emerald-500/5"
                    : "border-slate-700/80 bg-[#0f172a] hover:border-slate-500/80 hover:bg-[#0f172a]/80"
                }`}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileChange}
                  accept=".pdf"
                  className="hidden"
                />

                {resumeFile ? (
                  <div className="flex flex-col items-center text-center">
                    <div className="p-3 bg-emerald-500/10 text-emerald-400 rounded-xl border border-emerald-500/20 mb-3">
                      <FileText className="w-8 h-8" />
                    </div>
                    <p className="text-sm font-semibold text-slate-200">{resumeFile.name}</p>
                    <p className="text-xs text-slate-400 mt-1">
                      {(resumeFile.size / 1024).toFixed(1)} KB • PDF Document
                    </p>
                    <span className="text-xs text-emerald-400 mt-3 font-semibold flex items-center gap-1.5">
                      <CheckCircle className="w-4 h-4" />
                      Resume Loaded
                    </span>
                  </div>
                ) : (
                  <div className="flex flex-col items-center text-center">
                    <div className="p-3 bg-slate-800/80 text-slate-400 rounded-xl border border-slate-700/40 mb-3">
                      <Upload className="w-8 h-8" />
                    </div>
                    <p className="text-sm font-semibold text-slate-200">Drag & drop your PDF resume here</p>
                    <p className="text-xs text-slate-400 mt-1.5">
                      or click to browse local files (PDF only, max 5MB)
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Error alerts */}
            {welcomeError && (
              <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs font-semibold text-red-400 flex items-center gap-2">
                <span className="w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse" />
                {welcomeError}
              </div>
            )}

            {/* Submit CTA */}
            <button
              onClick={handleStartInterview}
              disabled={isProcessingPdf}
              className={`w-full py-3.5 px-4 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 shadow-lg shadow-blue-500/10 hover:shadow-blue-500/20 transition-all ${
                isProcessingPdf
                  ? "bg-slate-800 text-slate-400 cursor-not-allowed border border-slate-700"
                  : "bg-blue-600 hover:bg-blue-500 text-white font-bold"
              }`}
            >
              {isProcessingPdf ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Analyzing Resume Structure...
                </>
              ) : (
                <>
                  Start Technical Interview
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </section>
      )}

      {/* ═════════════════════════════════════════════════════════════════════
          VIEW B: Interactive Screening Chat Panel
          ═════════════════════════════════════════════════════════════════════ */}
      {screen === "CHAT" && (
        <section className="w-full max-w-4xl flex flex-col h-[75vh] glass rounded-2xl glow-blue z-10 animate-fade-in">
          {/* Interview Header Info */}
          <div className="px-6 py-4 border-b border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/40 rounded-t-2xl">
            <div className="flex items-center gap-3">
              <div className="w-2.5 h-2.5 bg-emerald-500 rounded-full animate-ping" />
              <div>
                <h3 className="font-bold text-sm text-slate-100">{selectedRole} Interview Session</h3>
                <p className="text-xs text-slate-400">
                  Extracted Skills: {skills.slice(0, 5).join(", ")}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="px-3 py-1 bg-blue-500/10 border border-blue-500/20 rounded-full text-xs font-semibold text-blue-400 flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" />
                Step {currentStep} of 5
              </div>
            </div>
          </div>

          {/* Conversation Bubbles */}
          <div className="flex-1 p-6 overflow-y-auto space-y-6">
            {chatLog.map((msg, index) => (
              <div
                key={index}
                className={`flex gap-3 max-w-[80%] ${
                  msg.sender === "USER" ? "ml-auto flex-row-reverse" : "mr-auto"
                }`}
              >
                {/* Avatar Icon */}
                <div
                  className={`w-9 h-9 rounded-xl flex items-center justify-center border flex-shrink-0 ${
                    msg.sender === "USER"
                      ? "bg-slate-800 border-slate-700 text-slate-200"
                      : "bg-blue-600/10 border-blue-500/20 text-blue-400"
                  }`}
                >
                  {msg.sender === "USER" ? <User className="w-4 h-4" /> : <Brain className="w-4 h-4" />}
                </div>

                {/* Bubble content */}
                <div>
                  <div
                    className={`p-4 rounded-2xl text-sm leading-relaxed ${
                      msg.sender === "USER"
                        ? "bg-blue-600 text-white rounded-tr-none"
                        : "bg-slate-800/80 text-slate-100 border border-slate-700/60 rounded-tl-none"
                    }`}
                  >
                    {msg.text}
                  </div>
                  <span className="text-[10px] text-slate-500 block mt-1.5 px-1">
                    {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              </div>
            ))}

            {/* AI Processing Skeleton / Indicator */}
            {isWaitingForAi && (
              <div className="flex gap-3 max-w-[80%] mr-auto">
                <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-blue-600/10 border border-blue-500/20 text-blue-400">
                  <Brain className="w-4 h-4 animate-pulse" />
                </div>
                <div className="bg-slate-800/50 border border-slate-700/40 p-4 rounded-2xl rounded-tl-none space-y-2 w-48">
                  <div className="h-2.5 bg-slate-700 rounded w-5/6 animate-pulse" />
                  <div className="h-2.5 bg-slate-700 rounded w-1/2 animate-pulse" />
                </div>
              </div>
            )}
          </div>

          {/* Form input */}
          <form
            onSubmit={handleSubmitAnswer}
            className="p-4 border-t border-slate-800 bg-[#0f172a]/30 rounded-b-2xl"
          >
            <div className="relative flex items-center bg-[#090d16] border border-slate-800 rounded-xl focus-within:border-blue-500 transition-colors">
              <textarea
                value={currentAnswer}
                onChange={(e) => setCurrentAnswer(e.target.value)}
                placeholder="Type your response here... (Press Shift+Enter to newline)"
                rows={1}
                disabled={isSubmitting}
                className="w-full bg-transparent px-4 py-3.5 pr-14 text-sm text-slate-100 placeholder-slate-500 outline-none resize-none"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmitAnswer(e);
                  }
                }}
              />
              <button
                type="submit"
                disabled={!currentAnswer.trim() || isSubmitting}
                className={`absolute right-3 p-2 rounded-lg transition-all ${
                  currentAnswer.trim() && !isSubmitting
                    ? "bg-blue-600 text-white hover:bg-blue-500 cursor-pointer"
                    : "text-slate-600 cursor-not-allowed"
                }`}
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
            <p className="text-[10px] text-slate-500 mt-2 px-1 text-center md:text-left">
              Note: Press <kbd className="font-sans border border-slate-800 px-1.5 py-0.5 rounded bg-slate-900 text-slate-400">Enter</kbd> to submit answer.
            </p>
          </form>
        </section>
      )}

      {/* ═════════════════════════════════════════════════════════════════════
          VIEW C: Performance Insights Screen
          ═════════════════════════════════════════════════════════════════════ */}
      {screen === "INSIGHTS" && (
        <section className="w-full max-w-5xl grid grid-cols-1 lg:grid-cols-3 gap-6 z-10 animate-fade-in">
          
          {/* Column A: Evaluation Report */}
          <div className="lg:col-span-2 space-y-6">
            <div className="glass p-6 md:p-8 rounded-2xl glow-blue">
              <div className="flex items-center gap-2.5 text-blue-400 mb-3">
                <Award className="w-5 h-5 animate-bounce" />
                <span className="text-xs font-bold uppercase tracking-wider">Evaluation Report</span>
              </div>
              <h2 className="text-2xl font-extrabold mb-6 tracking-tight">Performance Summary</h2>
              
              {/* Performance description */}
              <div className="prose prose-invert max-w-none text-sm text-slate-200 leading-relaxed space-y-4 whitespace-pre-line border-t border-slate-800/80 pt-6">
                {evaluationSummary}
              </div>
            </div>
          </div>

          {/* Column B: Transcript Tree */}
          <div className="lg:col-span-1 space-y-6">
            <div className="glass p-6 rounded-2xl flex flex-col max-h-[80vh] overflow-hidden">
              <div className="flex items-center gap-2.5 text-blue-400 mb-4 flex-shrink-0">
                <MessageSquare className="w-5 h-5" />
                <span className="text-xs font-bold uppercase tracking-wider">Q&A Transcript Tree</span>
              </div>

              {/* Scrollable list */}
              <div className="flex-1 overflow-y-auto space-y-4 pr-1">
                {historicalLogs.map((log, index) => (
                  <div key={index} className="p-3.5 bg-slate-900/50 border border-slate-800/80 rounded-xl space-y-3">
                    <div className="flex items-start gap-2">
                      <span className="text-[10px] font-bold px-2 py-0.5 bg-blue-600/20 text-blue-400 rounded-md border border-blue-500/10">
                        Q{index + 1}
                      </span>
                      <p className="text-xs font-semibold text-slate-200 leading-normal">{log.question}</p>
                    </div>

                    <div className="flex items-start gap-2 border-t border-slate-800/50 pt-2.5">
                      <span className="text-[10px] font-bold px-2 py-0.5 bg-slate-800 text-slate-400 rounded-md border border-slate-700/10">
                        A{index + 1}
                      </span>
                      <p className="text-xs text-slate-400 leading-relaxed italic">
                        &ldquo;{log.answer || "(no answer provided)"}&rdquo;
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Action */}
              <button
                onClick={handleRestart}
                className="w-full mt-4 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold flex items-center justify-center gap-2 shadow-lg shadow-blue-500/10 flex-shrink-0"
              >
                Start New Evaluation Session
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>

        </section>
      )}

      {/* Footer copyright */}
      <footer className="w-full max-w-5xl text-center text-[10px] text-slate-600 mt-12 py-4 border-t border-slate-900 z-10">
        © 2026 PG AGI Technical screening. Crafted with premium Next.js and Tailwind CSS tokens.
      </footer>
    </main>
  );
}
