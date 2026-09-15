import { TradesConsole } from "@/components/trades-console";

export default async function UserTradesPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ username?: string }>;
}) {
  const { id } = await params;
  const { username } = await searchParams;
  return <TradesConsole userId={Number(id)} username={username} />;
}
