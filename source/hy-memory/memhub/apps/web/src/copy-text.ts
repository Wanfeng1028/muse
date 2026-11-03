export async function copyText(text: string): Promise<void> {
  if (window.oneMemory?.copyText) {
    await window.oneMemory.copyText(text);
  } else {
    await navigator.clipboard.writeText(text);
  }
}
