"use client";

import { useState } from "react";
import { subscribe } from "@/lib/api";

type State = "idle" | "sending" | "done" | "error";

export default function SubscribeBox() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<State>("idle");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    setState((await subscribe(email)) ? "done" : "error");
  }

  if (state === "done") {
    return (
      <p className="font-mono text-xs text-gain">
        ✓ subscribed — the daily top-10 lands after each close.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-wrap items-center gap-2">
      <label htmlFor="email" className="sr-only">Email address</label>
      <input
        id="email"
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@example.com"
        className="w-56 border border-rule bg-panel px-3 py-1.5 font-mono text-xs text-bright placeholder:text-muted focus:border-cobalt focus:outline-none"
      />
      <button
        type="submit"
        disabled={state === "sending"}
        className="border border-cobalt bg-cobalt/10 px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-cobalt transition-colors hover:bg-cobalt hover:text-void disabled:opacity-50"
      >
        {state === "sending" ? "sending…" : "get the daily list"}
      </button>
      {state === "error" && (
        <span className="font-mono text-2xs text-loss">
          failed — check the address, try again
        </span>
      )}
    </form>
  );
}
