export type DaySchedule = { enabled: boolean; start: string; end: string };
export type WeeklySchedule = Record<string, DaySchedule>;

export const dayNames = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"];

export const defaultWeeklySchedule: WeeklySchedule = Object.fromEntries(
  dayNames.map((_, index) => [String(index), { enabled: true, start: "09:00", end: "22:00" }]),
);

const toMinutes = (value: string) => {
  const [hours, minutes] = value.split(":").map(Number);
  if (!Number.isInteger(hours) || !Number.isInteger(minutes) || hours < 0 || hours > 23 || minutes < 0 || minutes > 59) return null;
  return hours * 60 + minutes;
};

export function isStoreOpenNow(storeOpen: boolean, schedule?: WeeklySchedule): boolean {
  if (!storeOpen) return false;
  if (!schedule || Object.keys(schedule).length === 0) return true;

  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Dubai",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date());
  const weekday = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(parts.find((part) => part.type === "weekday")?.value ?? "");
  const hour = Number(parts.find((part) => part.type === "hour")?.value ?? 0) % 24;
  const minute = Number(parts.find((part) => part.type === "minute")?.value ?? 0);
  const today = schedule[String(weekday)];
  if (!today?.enabled) return false;

  const start = toMinutes(today.start);
  const end = toMinutes(today.end);
  if (start === null || end === null || start === end) return false;
  const current = hour * 60 + minute;
  return end > start ? current >= start && current < end : current >= start || current < end;
}
