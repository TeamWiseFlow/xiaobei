import { describe, expect, it } from "vitest";
import { stripThinkingFromText } from "./strip-thinking.js";

describe("stripThinkingFromText", () => {
  it("returns empty/falsy input unchanged", () => {
    expect(stripThinkingFromText("")).toBe("");
    expect(stripThinkingFromText(null as unknown as string)).toBe(null);
  });

  it("returns text without tags unchanged", () => {
    expect(stripThinkingFromText("Hello world")).toBe("Hello world");
  });

  it("strips <think>…</think> content", () => {
    expect(stripThinkingFromText("<think>internal reasoning</think>Answer")).toBe("Answer");
  });

  it("strips <thinking>…</thinking> content", () => {
    expect(stripThinkingFromText("<thinking>step by step</thinking>Result")).toBe("Result");
  });

  it("strips <thought>…</thought> content", () => {
    expect(stripThinkingFromText("<thought>hmm</thought>Done")).toBe("Done");
  });

  it("strips <antthinking>…</antthinking> content", () => {
    expect(stripThinkingFromText("<antthinking>plan</antthinking>Output")).toBe("Output");
  });

  it("strips <final> tags but keeps content", () => {
    expect(stripThinkingFromText("A <final>important</final> B")).toBe("A important B");
  });

  it("strips <relevant-memories>…</relevant-memories> content", () => {
    const input = "<relevant-memories>some context</relevant-memories>Visible";
    expect(stripThinkingFromText(input)).toBe("Visible");
  });

  it("strips <relevant_memories> variant", () => {
    const input = "<relevant_memories>ctx</relevant_memories>Visible";
    expect(stripThinkingFromText(input)).toBe("Visible");
  });

  it("handles mixed thinking + answer", () => {
    const input = "<think>Let me think about this carefully.</think>\n\n你好，请问有什么可以帮到您？";
    const result = stripThinkingFromText(input);
    expect(result).toBe("你好，请问有什么可以帮到您？");
  });

  it("handles Chinese model providers with loose whitespace in tags", () => {
    const input = "< think >reasoning</ think >Answer";
    expect(stripThinkingFromText(input)).toBe("Answer");
  });

  it("preserves thinking tags inside code blocks", () => {
    const input = "Here is code:\n```\n<think>this is a code example</think>\n```\nDone";
    expect(stripThinkingFromText(input)).toBe(
      "Here is code:\n```\n<think>this is a code example</think>\n```\nDone",
    );
  });

  it("handles unclosed thinking tag (preserve trailing text)", () => {
    const input = "<think>start of reasoning\nstill reasoning\nand the answer is here";
    // Unclosed tag → preserve trailing text (mode "preserve")
    const result = stripThinkingFromText(input);
    expect(result).toContain("and the answer is here");
  });

  it("handles multiple thinking blocks", () => {
    const input = "<think>first</think>A<thinking>second</thinking>B";
    expect(stripThinkingFromText(input)).toBe("AB");
  });

  it("trims leading whitespace after stripping", () => {
    const input = "<think>reasoning</think>   \n  Answer";
    expect(stripThinkingFromText(input)).toBe("Answer");
  });
});
