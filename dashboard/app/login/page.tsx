"use client";

import { useState } from "react";
import { Button, Card, Input } from "@/components/ui";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    setBusy(false);
    if (!response.ok) {
      setError("Invalid username or password");
      return;
    }
    window.location.href = "/";
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm p-6">
        <h1 className="text-xl font-semibold">Dashboard Login</h1>
        <p className="mt-1 text-sm text-muted">Sign in to Reddit Reply Ops.</p>
        <form className="mt-5 space-y-3" onSubmit={submit}>
          <Input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username" autoComplete="username" />
          <Input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" type="password" autoComplete="current-password" />
          {error && <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-danger">{error}</div>}
          <Button className="w-full" disabled={busy || !username || !password}>
            {busy ? "Signing in..." : "Sign In"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
