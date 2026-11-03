/** A command as `sh` reads it: words after quote removal, `;` as a word of its
 * own, and the script of `sh -c` read one level down between markers. Two
 * spellings the shell runs identically give equal lists. Null when the text
 * cannot be read as a whole (an unterminated quote or a trailing escape). */
export function shellWords(command: string): string[] | null {
  const words = split(command);
  if (words === null) return null;
  if (words.length >= 3 && words[0] === "sh" && words[1] === "-c") {
    const script = shellWords(words[2] as string);
    if (script === null) return null;
    return ["sh", "-c", "(", ...script, ")", ...words.slice(3)];
  }
  return words;
}

export function sameShellCommand(left: string, right: string): boolean {
  const a = shellWords(left);
  const b = shellWords(right);
  return (
    a !== null &&
    b !== null &&
    a.length === b.length &&
    a.every((word, index) => word === b[index])
  );
}

function split(text: string): string[] | null {
  const words: string[] = [];
  let word = "";
  let started = false;
  let quote: "'" | '"' | null = null;
  const end = () => {
    if (started) words.push(word);
    word = "";
    started = false;
  };
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index] as string;
    if (quote === "'") {
      if (char === "'") quote = null;
      else word += char;
      continue;
    }
    if (quote === '"') {
      if (char === '"') quote = null;
      else if (char === "\\" && '$`"\\\n'.includes(text[index + 1] ?? "")) {
        index += 1;
        if (text[index] !== "\n") word += text[index];
      } else word += char;
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      started = true;
    } else if (char === "\\") {
      index += 1;
      if (index >= text.length) return null;
      if (text[index] !== "\n") {
        word += text[index];
        started = true;
      }
    } else if (char === " " || char === "\t" || char === "\n") end();
    else if (char === ";") {
      end();
      words.push(";");
    } else {
      word += char;
      started = true;
    }
  }
  if (quote !== null) return null;
  end();
  return words;
}
