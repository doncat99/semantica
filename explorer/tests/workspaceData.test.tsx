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

test("reasoning displays readable relationships and sends selected stable facts", async () => {
  const relation = { id: "edge-opaque-1", source_id: "node-opaque-1", source_label: "Source concept", target_id: "node-opaque-2", target_label: "Claim concept", type: "supports", fact: "supports(node-opaque-1, node-opaque-2)" };
  let submitted: Record<string, unknown> | undefined;
  globalThis.fetch = async (url, options) => {
    if (String(url).startsWith("/api/reason/facts")) return Response.json({ relations: [relation], relationship_types: [{ type: "supports", count: 1 }], offset: 0, limit: 100, total: 1, has_more: false, skipped_edges: 0 });
    submitted = JSON.parse(String(options?.body));
    return Response.json({ inferred_facts: [], rules_fired: 1, added_edges: 0, mutated: false });
  };
  const view = render(<QueryClientProvider client={new QueryClient()}><ReasoningWorkspace /></QueryClientProvider>);
  await view.findByText("Source concept");
  assert.equal(view.queryByText(/node-opaque/), null);
  fireEvent.click(view.getByRole("checkbox", { name: "Select Source concept supports Claim concept" }));
  fireEvent.change(view.getByLabelText("Rules"), { target: { value: "IF supports(X, Y) THEN related(X, Y)" } });
  fireEvent.click(view.getByRole("button", { name: "Run Reasoning" }));
  await waitFor(() => assert.deepEqual(submitted?.facts, ["supports(node-opaque-1, node-opaque-2)"]));
  assert.equal(submitted?.rules instanceof Array, true);
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
