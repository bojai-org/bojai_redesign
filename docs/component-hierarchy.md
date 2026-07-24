# BojAI Frontend Component Hierarchy

This document defines the proposed frontend component structure for the BojAI healthcare chatbot and agent builder.

The hierarchy is based on the existing static HTML mock and is organized by product domain rather than by the original monolithic file.

---

## 1. Application hierarchy

```text
App
├── AppProviders
│   ├── AuthProvider
│   ├── ToastProvider
│   ├── QueryClientProvider
│   └── WorkspaceProvider
│
├── AppRouter
│   ├── ProjectsRoute
│   │   └── ProjectsPage
│   │       ├── AppHeader
│   │       │   ├── Brand
│   │       │   ├── Breadcrumbs
│   │       │   ├── DocsButton
│   │       │   └── UserAvatar
│   │       │
│   │       ├── ProjectsHero
│   │       │   ├── HeroCopy
│   │       │   └── CreateProjectButton
│   │       │
│   │       ├── ProjectStatsGrid
│   │       │   └── ProjectStatCard[]
│   │       │
│   │       └── ProjectGrid
│   │           ├── NewProjectCard
│   │           └── ProjectCard[]
│   │               ├── PipelineThumbnail
│   │               ├── ProjectSummary
│   │               ├── TagList
│   │               └── ProjectMetadata
│   │
│   └── ProjectRoute
│       └── ProjectWorkspacePage
│           ├── AppHeader
│           ├── ProjectNavigation
│           │   └── ProjectTab[]
│           │
│           └── ProjectTabOutlet
│               ├── PipelinePage
│               ├── PromptsPage
│               ├── EvaluationPage
│               └── ProjectSettingsPage
```

---

## 2. Route hierarchy

```text
/
└── ProjectsPage

/projects/:projectId
├── /pipeline
├── /prompts
├── /evaluation
└── /settings
```

Recommended initial routes:

```text
/
/projects/:projectId/pipeline
/projects/:projectId/prompts
/projects/:projectId/evaluation
/projects/:projectId/settings
```

---

## 3. Pipeline editor hierarchy

The pipeline editor is the most complex area and should be treated as a feature module with its own state, components, utilities, and schemas.

```text
PipelinePage
├── PipelineProvider
│
├── PipelineLayout
│   ├── AgentPalette
│   │   ├── PaletteInstructions
│   │   ├── AgentCategory
│   │   │   ├── SafetyAgentPaletteItem[]
│   │   │   └── AnswerAgentPaletteItem[]
│   │   └── ResetPipelineButton
│   │
│   └── PipelineEditor
│       ├── PipelineToolbar
│       │   ├── PipelineIdentity
│       │   ├── AutosaveStatus
│       │   ├── ValidatePipelineButton
│       │   └── SavePipelineButton
│       │
│       ├── WorkflowCanvas
│       │   ├── CanvasBackground
│       │   ├── SafetyBarrierZone
│       │   │   ├── BarrierLabel
│       │   │   ├── BarrierEmptyState
│       │   │   └── SafetyNode[]
│       │   │
│       │   ├── WorkflowNode[]
│       │   │   ├── NodeIcon
│       │   │   ├── NodeContent
│       │   │   ├── InputPort
│       │   │   ├── OutputPort
│       │   │   └── DeleteNodeButton
│       │   │
│       │   ├── WorkflowEdgeLayer
│       │   │   ├── WorkflowEdge[]
│       │   │   ├── EdgeLabel
│       │   │   ├── DeleteEdgeControl
│       │   │   └── TemporaryConnectionEdge
│       │   │
│       │   └── CanvasInteractionLayer
│       │       ├── NodeDragHandler
│       │       ├── NodeDropHandler
│       │       ├── ConnectionHandler
│       │       ├── SelectionHandler
│       │       └── KeyboardShortcutHandler
│       │
│       ├── NodeInspector
│       │   ├── NodeSummary
│       │   ├── EditPromptButton
│       │   ├── NodeConfigurationForm
│       │   └── DeleteNodeButton
│       │
│       └── PipelineLegend
```

### Generic workflow node

Use one reusable node shell, driven by a node registry.

```text
WorkflowNode
├── NodeFrame
├── NodeIcon
├── NodeTitle
├── NodeSubtitle
├── InputPort
├── OutputPort
└── NodeActions
```

Recommended node definition:

```ts
type NodeDefinition = {
  type: string;
  category: "system" | "safety" | "answer";
  label: string;
  description: string;
  icon: React.ComponentType;
  defaultConfig: Record<string, unknown>;
  configSchema: unknown;
  configurationComponent?: React.ComponentType;
  canDelete: boolean;
  hasInput: boolean;
  hasOutput: boolean;
};
```

Recommended registry:

```ts
const nodeRegistry = {
  user_query: userQueryDefinition,
  relevance_check: relevanceCheckDefinition,
  rejected: rejectedDefinition,
  static_filter: staticFilterDefinition,
  simple_filter: simpleFilterDefinition,
  llm_filter: llmFilterDefinition,
  choice_agent: choiceAgentDefinition,
  coding_agent: codingAgentDefinition,
  retrieval_agent: retrievalAgentDefinition,
  keyword_agent: keywordAgentDefinition,
  sufficient_check: sufficientCheckDefinition,
  final_answer: finalAnswerDefinition,
};
```

---

## 4. Prompts hierarchy

```text
PromptsPage
├── PromptsProvider
│
└── PromptsLayout
    ├── PromptSidebar
    │   ├── PromptList
    │   │   └── PromptListItem[]
    │   └── PromptStatusIndicator
    │
    └── PromptEditorPanel
        ├── PromptEditorHeader
        │   ├── PromptTitle
        │   ├── PromptDescription
        │   └── PromptMetadataBadge
        │
        ├── PromptVariableList
        │   └── PromptVariableChip[]
        │
        ├── PromptTextarea
        │
        └── PromptEditorActions
            ├── RevertPromptButton
            └── SavePromptButton
```

Initial prompt types:

```text
Choice Agent Prompt
Retrieval Agent Prompt
Keyword Retrieval Agent Prompt
Final Answer Prompt
LLM Safety Filter Prompt
```

Recommended prompt model:

```ts
type PromptDefinition = {
  id: string;
  name: string;
  description: string;
  variables: string[];
  content: string;
  version: number;
  updatedAt: string;
  linkedNodeTypes: string[];
};
```

---

## 5. Evaluation hierarchy

```text
EvaluationPage
├── EvaluationProvider
│
├── EvaluationDatasetCard
│   ├── EvaluationDatasetHeader
│   │   └── DatasetModeSelector
│   │       ├── ManualModeButton
│   │       └── CsvUploadModeButton
│   │
│   ├── DatasetInputPanel
│   │   ├── ManualDatasetEditor
│   │   │   ├── EvaluationDatasetTable
│   │   │   │   └── EvaluationDatasetRow[]
│   │   │   │       ├── QuestionInput
│   │   │   │       ├── ExpectedAnswerInput
│   │   │   │       ├── ExpectedDocumentInput
│   │   │   │       └── RemoveRowButton
│   │   │   └── AddRowButton
│   │   │
│   │   └── CsvDatasetUploader
│   │       ├── CsvDropzone
│   │       ├── HiddenFileInput
│   │       ├── UploadedFileSummary
│   │       └── CsvValidationErrors
│   │
│   └── EvaluationRunControls
│       ├── DatasetSummary
│       └── RunEvaluationButton
│
└── EvaluationResults
    ├── EvaluationResultsHeader
    ├── EvaluationMetricsGrid
    │   └── EvaluationMetricCard[]
    │
    ├── EvaluationResultsTable
    │   └── EvaluationResultRow[]
    │       ├── QuestionCell
    │       ├── ExpectedAnswerCell
    │       ├── SystemAnswerCell
    │       ├── SimilarityIndicator
    │       ├── ExpectedDocumentCell
    │       ├── RetrievedDocumentCell
    │       └── MatchBadge
    │
    └── EvaluationResultsActions
        ├── ShowAllResultsButton
        └── ExportResultsButton
```

Future evaluation components:

```text
EvaluationRunHistory
EvaluationRunDetails
EvaluationMetricSelector
SafetyEvaluationSummary
LatencyBreakdown
FailureInspector
PerNodeTrace
DatasetVersionSelector
PipelineVersionSelector
PromptVersionSelector
```

---

## 6. Settings hierarchy

```text
ProjectSettingsPage
├── ProjectDetailsCard
│   ├── ProjectNameField
│   ├── ProjectDescriptionField
│   ├── OwnerField
│   └── OwnerEmailField
│
├── LlmConfigurationCard
│   ├── ProviderSelector
│   │   └── ProviderOption[]
│   │
│   ├── ProviderConfigurationPanel
│   │   ├── AwsBedrockConfiguration
│   │   ├── AnthropicConfiguration
│   │   └── OpenAiConfiguration
│   │
│   └── ProviderActions
│       ├── TestConnectionButton
│       └── SaveConfigurationButton
│
└── DangerZoneCard
    ├── ArchiveProjectButton
    └── DeleteProjectButton
```

Shared form components:

```text
FormField
TextInput
PasswordInput
SecretInput
TextArea
SelectInput
ProviderCard
ConfirmationDialog
SaveButton
LoadingButton
InlineError
```

---

## 7. Shared UI components

```text
components/
├── layout/
│   ├── AppHeader
│   ├── PageContainer
│   ├── SplitPane
│   └── StickyToolbar
│
├── navigation/
│   ├── Breadcrumbs
│   ├── Tabs
│   └── TabButton
│
├── feedback/
│   ├── Toast
│   ├── Alert
│   ├── EmptyState
│   ├── ErrorState
│   ├── LoadingSpinner
│   └── Skeleton
│
├── forms/
│   ├── FormField
│   ├── TextInput
│   ├── TextArea
│   ├── Select
│   ├── SecretInput
│   └── SegmentedControl
│
├── data-display/
│   ├── Card
│   ├── Badge
│   ├── Tag
│   ├── MetricCard
│   └── DataTable
│
└── actions/
    ├── Button
    ├── IconButton
    ├── DeleteButton
    └── ConfirmationDialog
```

---

## 8. Frontend state categories

### Server state

```text
projects
currentProject
workflow
workflowVersions
prompts
providerConfiguration
evaluationDatasets
evaluationRuns
evaluationResults
```

### Persisted editor state

```text
nodes
edges
node configuration
node positions
pipeline metadata
prompt content
model configuration
evaluation datasets
```

### Local interaction state

```text
active project tab
selected node ID
currently dragged node
temporary connection
canvas viewport
zoom level
open inspector
selected prompt
selected provider tab
dataset entry mode
show all evaluation rows
toast visibility
modal visibility
```

Recommended pipeline editor state:

```ts
type PipelineEditorState = {
  selectedNodeId: string | null;
  draggedNodeType: string | null;
  connectionStartNodeId: string | null;
  connectionPreview: {
    x: number;
    y: number;
  } | null;
  viewport: {
    x: number;
    y: number;
    zoom: number;
  };
  isInspectorOpen: boolean;
  isDirty: boolean;
};
```

---

## 9. Suggested folder structure

```text
src/
├── app/
│   ├── App.tsx
│   ├── router.tsx
│   └── providers.tsx
│
├── components/
│   ├── actions/
│   ├── data-display/
│   ├── feedback/
│   ├── forms/
│   ├── layout/
│   └── navigation/
│
├── features/
│   ├── projects/
│   │   ├── api/
│   │   ├── components/
│   │   ├── data/
│   │   ├── hooks/
│   │   ├── pages/
│   │   ├── schemas/
│   │   └── types/
│   │
│   ├── pipeline/
│   │   ├── api/
│   │   ├── canvas/
│   │   ├── components/
│   │   ├── data/
│   │   ├── hooks/
│   │   ├── nodes/
│   │   │   ├── nodeRegistry.ts
│   │   │   ├── definitions/
│   │   │   └── configuration/
│   │   ├── schemas/
│   │   ├── state/
│   │   ├── types/
│   │   └── utils/
│   │
│   ├── prompts/
│   │   ├── api/
│   │   ├── components/
│   │   ├── data/
│   │   ├── schemas/
│   │   └── types/
│   │
│   ├── evaluations/
│   │   ├── api/
│   │   ├── components/
│   │   ├── data/
│   │   ├── schemas/
│   │   ├── types/
│   │   └── utils/
│   │
│   └── settings/
│       ├── api/
│       ├── components/
│       ├── providers/
│       ├── schemas/
│       └── types/
│
├── lib/
│   ├── apiClient.ts
│   ├── queryClient.ts
│   ├── errors.ts
│   └── validation.ts
│
├── styles/
│   ├── tokens.css
│   └── global.css
│
└── types/
    └── shared.ts
```

---

## 10. Architectural boundary

Keep these layers separate:

```text
Canvas rendering
≠ workflow business logic
≠ backend execution
```

The canvas edits a serialized workflow definition.

The backend validates and executes that definition.

The evaluation system invokes a saved workflow version.
