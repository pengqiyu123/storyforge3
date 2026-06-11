import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function countChineseChars(text: string): number {
  const matches = text.match(/[\u4e00-\u9fff\u3400-\u4dbf]/g);
  return matches ? matches.length : 0;
}
