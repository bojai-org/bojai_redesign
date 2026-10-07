import type { ReactNode } from "react";
import styles from "./Markdown.module.css";

export interface MarkdownProps {
  content: string;
}

type Block =
  | { kind: "heading"; level: 1 | 2 | 3 | 4 | 5 | 6; text: string }
  | { kind: "code"; code: string }
  | { kind: "quote"; lines: string[] }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "hr" }
  | { kind: "paragraph"; text: string };

const FENCE_RE = /^```\w*\s*$/;
const HR_RE = /^(-{3,}|\*{3,}|_{3,})$/;
const HEADING_RE = /^(#{1,6})\s+(.*)$/;
const QUOTE_RE = /^>\s?/;
const UL_RE = /^[-*+]\s+/;
const OL_RE = /^\d+[.)]\s+/;

function isBlockBoundary(line: string): boolean {
  const trimmed = line.trim();
  return (
    trimmed === "" ||
    FENCE_RE.test(trimmed) ||
    HR_RE.test(trimmed) ||
    HEADING_RE.test(line) ||
    QUOTE_RE.test(line) ||
    UL_RE.test(line) ||
    OL_RE.test(line)
  );
}

/** Small hand-rolled parser covering the markdown LLM answers actually use
 * (headings, paragraphs, lists, blockquotes, fenced code, emphasis, links) --
 * intentionally not a full CommonMark implementation. Renders straight to
 * React elements (never dangerouslySetInnerHTML) so untrusted model output
 * can't inject HTML. */
function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      i++;
      continue;
    }

    if (FENCE_RE.test(line.trim())) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && lines[i].trim() !== "```") {
        codeLines.push(lines[i]);
        i++;
      }
      i++;
      blocks.push({ kind: "code", code: codeLines.join("\n") });
      continue;
    }

    if (HR_RE.test(line.trim())) {
      blocks.push({ kind: "hr" });
      i++;
      continue;
    }

    const headingMatch = HEADING_RE.exec(line);
    if (headingMatch) {
      blocks.push({
        kind: "heading",
        level: headingMatch[1].length as 1 | 2 | 3 | 4 | 5 | 6,
        text: headingMatch[2].trim(),
      });
      i++;
      continue;
    }

    if (QUOTE_RE.test(line)) {
      const quoteLines: string[] = [];
      while (i < lines.length && QUOTE_RE.test(lines[i])) {
        quoteLines.push(lines[i].replace(QUOTE_RE, ""));
        i++;
      }
      blocks.push({ kind: "quote", lines: quoteLines });
      continue;
    }

    if (UL_RE.test(line)) {
      const items: string[] = [];
      while (i < lines.length && UL_RE.test(lines[i])) {
        items.push(lines[i].replace(UL_RE, ""));
        i++;
      }
      blocks.push({ kind: "ul", items });
      continue;
    }

    if (OL_RE.test(line)) {
      const items: string[] = [];
      while (i < lines.length && OL_RE.test(lines[i])) {
        items.push(lines[i].replace(OL_RE, ""));
        i++;
      }
      blocks.push({ kind: "ol", items });
      continue;
    }

    const paraLines: string[] = [line];
    i++;
    while (i < lines.length && !isBlockBoundary(lines[i])) {
      paraLines.push(lines[i]);
      i++;
    }
    blocks.push({ kind: "paragraph", text: paraLines.join(" ") });
  }

  return blocks;
}

function isSafeUrl(url: string): boolean {
  if (url.startsWith("#") || url.startsWith("/")) return true;
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.protocol === "http:" || parsed.protocol === "https:" || parsed.protocol === "mailto:";
  } catch {
    return false;
  }
}

const INLINE_RE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(__[^_]+__)|(\[[^\]]+\]\([^)]+\))|(\*[^*]+\*)|(_[^_]+_)/g;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;
  INLINE_RE.lastIndex = 0;

  while ((match = INLINE_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    const nodeKey = `${keyPrefix}-${key++}`;

    if (token.startsWith("`")) {
      nodes.push(
        <code key={nodeKey} className={styles.inlineCode}>
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("**") || token.startsWith("__")) {
      nodes.push(<strong key={nodeKey}>{renderInline(token.slice(2, -2), nodeKey)}</strong>);
    } else if (token.startsWith("[")) {
      const linkMatch = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      if (linkMatch) {
        const [, label, url] = linkMatch;
        nodes.push(
          isSafeUrl(url) ? (
            <a key={nodeKey} href={url} target="_blank" rel="noopener noreferrer">
              {renderInline(label, nodeKey)}
            </a>
          ) : (
            label
          ),
        );
      } else {
        nodes.push(token);
      }
    } else {
      nodes.push(<em key={nodeKey}>{renderInline(token.slice(1, -1), nodeKey)}</em>);
    }

    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}

function renderHeading(block: Extract<Block, { kind: "heading" }>, key: string): ReactNode {
  const content = renderInline(block.text, key);
  switch (block.level) {
    case 1:
      return (
        <h1 key={key} className={styles.heading}>
          {content}
        </h1>
      );
    case 2:
      return (
        <h2 key={key} className={styles.heading}>
          {content}
        </h2>
      );
    case 3:
      return (
        <h3 key={key} className={styles.heading}>
          {content}
        </h3>
      );
    case 4:
      return (
        <h4 key={key} className={styles.heading}>
          {content}
        </h4>
      );
    case 5:
      return (
        <h5 key={key} className={styles.heading}>
          {content}
        </h5>
      );
    case 6:
      return (
        <h6 key={key} className={styles.heading}>
          {content}
        </h6>
      );
  }
}

function renderBlock(block: Block, index: number): ReactNode {
  const key = `b-${index}`;

  switch (block.kind) {
    case "heading":
      return renderHeading(block, key);
    case "code":
      return (
        <pre key={key} className={styles.codeBlock}>
          <code>{block.code}</code>
        </pre>
      );
    case "quote":
      return (
        <blockquote key={key} className={styles.quote}>
          {block.lines.map((line, i) => (
            <p key={`${key}-${i}`}>{renderInline(line, `${key}-${i}`)}</p>
          ))}
        </blockquote>
      );
    case "ul":
      return (
        <ul key={key} className={styles.list}>
          {block.items.map((item, i) => (
            <li key={`${key}-${i}`}>{renderInline(item, `${key}-${i}`)}</li>
          ))}
        </ul>
      );
    case "ol":
      return (
        <ol key={key} className={styles.list}>
          {block.items.map((item, i) => (
            <li key={`${key}-${i}`}>{renderInline(item, `${key}-${i}`)}</li>
          ))}
        </ol>
      );
    case "hr":
      return <hr key={key} className={styles.hr} />;
    case "paragraph":
      return (
        <p key={key} className={styles.paragraph}>
          {renderInline(block.text, key)}
        </p>
      );
  }
}

export function Markdown({ content }: MarkdownProps) {
  const blocks = parseBlocks(content);
  return <div className={styles.markdown}>{blocks.map(renderBlock)}</div>;
}
