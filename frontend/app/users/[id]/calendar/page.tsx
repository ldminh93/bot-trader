import { CalendarConsole } from "@/components/calendar-console";

export default async function UserCalendarPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ username?: string }>;
}) {
  const { id } = await params;
  const { username } = await searchParams;
  return <CalendarConsole userId={Number(id)} username={username} />;
}
