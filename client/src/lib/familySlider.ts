export function getCyclicSlideIndex(current: number, direction: -1 | 1, total: number): number {
  if (!Number.isInteger(total) || total <= 0) return 0;
  return ((current + direction) % total + total) % total;
}
