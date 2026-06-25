"use client";

import { Pulse } from "@phosphor-icons/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "register") {
        await api.register(email, password);
      }
      await api.login(email, password);
      router.push("/dashboard");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  const isLogin = mode === "login";
  return (
    <main className="grid min-h-[100dvh] place-items-center px-4 py-10">
      <div className="w-full max-w-[420px]">
        <div className="mb-8 flex items-center gap-3">
          <div className="grid size-10 place-items-center rounded-[var(--radius)] bg-[var(--accent)] text-[var(--accent-ink)]">
            <Pulse size={22} weight="bold" />
          </div>
          <div>
            <p className="font-bold">Futures Operator</p>
            <p className="text-sm text-[var(--muted)]">Automated execution with hard safety gates</p>
          </div>
        </div>
        <form
          onSubmit={submit}
          className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--surface)] p-6"
        >
          <h1 className="text-2xl font-bold tracking-tight">
            {isLogin ? "Sign in to your console" : "Create your operator account"}
          </h1>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
            Paper trading works without exchange credentials. Live orders remain disabled by default.
          </p>
          <div className="mt-6 grid gap-5">
            <label className="grid gap-2 text-sm font-semibold">
              Email
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="h-11 rounded-[var(--radius)] border border-[var(--line-strong)] bg-[var(--background)] px-3 font-normal outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)]"
                placeholder="trader@example.com"
              />
            </label>
            <label className="grid gap-2 text-sm font-semibold">
              Password
              <input
                type="password"
                autoComplete={isLogin ? "current-password" : "new-password"}
                minLength={8}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="h-11 rounded-[var(--radius)] border border-[var(--line-strong)] bg-[var(--background)] px-3 font-normal outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)]"
                placeholder="At least 8 characters"
              />
            </label>
          </div>
          {error && (
            <p className="mt-4 rounded-[var(--radius)] border border-[var(--negative)]/40 bg-[var(--negative)]/10 p-3 text-sm text-[#ff9b9b]">
              {error}
            </p>
          )}
          <Button className="mt-6 w-full" size="lg" disabled={loading}>
            {loading ? "Working..." : isLogin ? "Sign in" : "Create account"}
          </Button>
          <p className="mt-5 text-center text-sm text-[var(--muted)]">
            {isLogin ? "New here?" : "Already registered?"}{" "}
            <Link
              className="font-semibold text-[var(--accent)] hover:underline"
              href={isLogin ? "/register" : "/login"}
            >
              {isLogin ? "Create account" : "Sign in"}
            </Link>
          </p>
        </form>
      </div>
    </main>
  );
}

