import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost" });
Object.assign(globalThis, { React, window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement, Node: dom.window.Node });
Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
const { cleanup, render, fireEvent, waitFor } = await import("@testing-library/react");
const { ReasoningWorkspace } = await import("../src/workspaces/ReasoningWorkspace.tsx");
const { DecisionWorkspace } = await import("../src/workspaces/DecisionWorkspace/DecisionWorkspace.tsx");
test.afterEach(cleanup);

test("reasoning starts from loaded graph facts and resets to them", async () => {
  globalThis.fetch = async () => Response.json({ facts: ["supports(source, claim)"], skipped_edges: 0 });
  const view = render(<QueryClientProvider client={new QueryClient()}><ReasoningWorkspace /></QueryClientProvider>);
  await waitFor(() => assert.equal((view.getByLabelText("Current graph facts") as HTMLTextAreaElement).value, "supports(source, claim)"));
  fireEvent.click(view.getByRole("button", { name: "Drug Candidate" }));
  fireEvent.click(view.getByRole("button", { name: /Reset/ }));
  assert.equal((view.getByLabelText("Current graph facts") as HTMLTextAreaElement).value, "supports(source, claim)");
  assert.equal((view.getByLabelText("Rules") as HTMLTextAreaElement).value, "");
});

test("decisions can be recorded through the native endpoint", async () => {
  const record = { decision_id: "decision-1", category: "research", scenario: "Review source", reasoning: "Source supports claim", outcome: "accepted", confidence: 0.8 };
  let submitted: unknown;
  globalThis.fetch = async (url, options) => {
    if (options?.method === "POST") {
      submitted = JSON.parse(String(options.body));
      return Response.json(record, { status: 201 });
    }
    return Response.json(String(url).endsWith("/chain") ? { chain: [] } : []);
  };
  const view = render(<DecisionWorkspace />);
  await view.findByText("No decisions");
  fireEvent.click(view.getByRole("button", { name: "Record decision" }));
  for (const field of ["category", "scenario", "reasoning", "outcome"] as const) fireEvent.change(view.getByLabelText(field), { target: { value: record[field] } });
  fireEvent.click(view.getByRole("button", { name: "Save decision" }));
  const { decision_id: _id, ...fields } = record;
  await waitFor(() => assert.deepEqual(submitted, { ...fields, entities: [] }));
  await view.findByText(/Source supports claim/);
});
