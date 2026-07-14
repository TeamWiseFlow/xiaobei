/** Ref registry: maps @e1, @e2 to aria role+name for Playwright locators. */

export interface RefEntry {
  ref: string;
  role: string;
  name: string;
  nth: number;
}

const INTERACTIVE_ROLES = new Set([
  "link", "button", "combobox", "textbox", "textarea",
  "checkbox", "radio", "switch", "slider",
  "tab", "tabpanel", "menuitem", "option",
  "select", "listbox", "searchbox",
]);

const ARIA_LINE_RE = /^(\s*-\s+)(\w+)(?:\s+"([^"]*)")?/;

export class RefRegistry {
  private entries = new Map<string, RefEntry>();
  private counter = 0;

  buildFromSnapshot(ariaText: string, interactiveOnly: boolean = false): string {
    this.entries.clear();
    this.counter = 0;

    const seen = new Map<string, number>();
    const lines = ariaText.split("\n");
    const resultLines: string[] = [];

    for (const line of lines) {
      const m = line.match(ARIA_LINE_RE);
      if (!m) {
        if (!interactiveOnly) resultLines.push(line);
        continue;
      }

      const role = m[2];
      const name = m[3] || "";

      if (interactiveOnly && !INTERACTIVE_ROLES.has(role)) continue;

      const key = `${role}\0${name}`;
      const nth = seen.get(key) || 0;
      seen.set(key, nth + 1);

      this.counter++;
      const ref = `e${this.counter}`;
      this.entries.set(ref, { ref, role, name, nth });

      resultLines.push(`${line.trimEnd()} [ref=${ref}]`);
    }

    return resultLines.join("\n");
  }

  resolve(refStr: string): RefEntry | undefined {
    const ref = refStr.replace(/^@/, "");
    return this.entries.get(ref);
  }

  get size(): number {
    return this.entries.size;
  }
}
