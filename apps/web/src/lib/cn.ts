import clsx, { type ClassValue } from "clsx";

/** Thin clsx wrapper — kept as one shared function per "no duplicated components." */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
