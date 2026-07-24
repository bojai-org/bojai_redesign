import type { ProjectSummary } from "../types/project";

export const mockProjects: ProjectSummary[] = [
  {
    id: "bipolar-support-bot",
    name: "Bipolar Disorder Support Bot",
    description:
      "Safety-gated Q&A assistant over the CREST.BD self-management resource library.",
    owner: "Soghomon",
    lastModified: "2026-07-15T09:30:00Z",
    tags: ["Retrieval + Choice", "3 safety layers"],
    status: "active",
    pipelinePreview: [
      { id: "p1", tone: "teal" },
      { id: "p2", tone: "purple" },
      { id: "p3", tone: "dark" },
    ],
    model: "claude-sonnet-4-5",
    evaluationCount: 10,
  },
  {
    id: "diabetes-coaching-assistant",
    name: "Diabetes Coaching Assistant",
    description:
      "Keyword-retrieval pipeline for nutrition & medication adherence FAQs.",
    owner: "Priya Raman",
    lastModified: "2026-07-13T14:05:00Z",
    tags: ["Keyword Retrieval", "1 safety layer"],
    status: "draft",
    pipelinePreview: [
      { id: "p1", tone: "teal" },
      { id: "p2", tone: "dark" },
    ],
    model: "gpt-4.1",
    evaluationCount: 4,
  },
  {
    id: "post-op-recovery-triage",
    name: "Post-Op Recovery Triage",
    description: "Coding + choice agent hybrid for symptom-severity routing.",
    owner: "Marcus Webb",
    lastModified: "2026-07-08T11:00:00Z",
    tags: ["Coding Agent", "2 safety layers"],
    status: "archived",
    pipelinePreview: [
      { id: "p1", tone: "teal" },
      { id: "p2", tone: "purple" },
      { id: "p3", tone: "purple" },
    ],
  },
  {
    id: "prenatal-nutrition-guide",
    name: "Prenatal Nutrition Guide",
    description:
      "Semantic search assistant over trimester-specific nutrition guidance.",
    owner: "Elena Torres",
    lastModified: "2026-07-15T07:45:00Z",
    tags: ["Retrieval Agent", "Single-layer safety"],
    status: "active",
    pipelinePreview: [
      { id: "p1", tone: "teal" },
      { id: "p2", tone: "dark" },
    ],
    model: "anthropic.claude-3-5-sonnet-20241022-v2:0",
    evaluationCount: 18,
  },
  {
    id: "medication-adherence-reminder",
    name: "Medication Adherence Reminder",
    description:
      "Choice-agent flow that routes refill, dosage, and side-effect questions.",
    owner: "Soghomon",
    lastModified: "2026-07-11T16:20:00Z",
    tags: ["Choice Agent"],
    status: "draft",
    pipelinePreview: [{ id: "p1", tone: "purple" }],
  },
  {
    id: "wound-care-faq",
    name: "Post-Surgical Wound Care FAQ",
    description:
      "Keyword-retrieval bot answering dressing-change and infection-warning-sign questions.",
    owner: "Aiden Clarke",
    lastModified: "2026-07-14T08:10:00Z",
    tags: ["Keyword Retrieval", "2 safety layers"],
    status: "active",
    pipelinePreview: [
      { id: "p1", tone: "teal" },
      { id: "p2", tone: "purple" },
      { id: "p3", tone: "dark" },
    ],
    model: "claude-sonnet-4-5",
    evaluationCount: 7,
  },
  {
    id: "chronic-pain-self-management",
    name: "Chronic Pain Self-Management",
    description:
      "Retrieval + choice pipeline over pacing, flare-up, and coping-strategy resources.",
    owner: "Priya Raman",
    lastModified: "2026-06-24T13:00:00Z",
    tags: ["Retrieval + Choice"],
    status: "archived",
    pipelinePreview: [
      { id: "p1", tone: "teal" },
      { id: "p2", tone: "purple" },
    ],
    evaluationCount: 2,
  },
  {
    id: "smoking-cessation-coach",
    name: "Smoking Cessation Coach",
    description:
      "Coding agent that tracks quit-date milestones and suggests craving-management techniques.",
    owner: "Marcus Webb",
    lastModified: "2026-07-15T06:00:00Z",
    tags: ["Coding Agent", "1 safety layer"],
    status: "draft",
    pipelinePreview: [
      { id: "p1", tone: "teal" },
      { id: "p2", tone: "dark" },
    ],
    model: "gpt-4.1",
  },
];
