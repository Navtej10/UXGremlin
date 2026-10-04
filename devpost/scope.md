---
doc: scope
status: approved
---

# UXGremlin

An autonomous AI agent that behaves like a difficult user to test a website's UX and report on friction points.

## The Unique Kernel
Instead of testing "does this website work technically?" or providing static AI critiques of a screenshot, UXGremlin tests "can a difficult user actually accomplish something on it?" by having an AI literally experience and navigate the site in a real browser.

## Who It's For
Product owners, designers, and developers who want to identify exactly where and why users get confused or abandon tasks. Today, they usually rely on lagging analytics, expensive manual user testing, or generic LLM feedback.

## The Core Loop
The user enters a website URL, a task, and selects a "Saboteur Persona" (like the Impatient User). They watch a live browser session as the AI attempts the task, and finally receive a Sabotage Report detailing the friction score, backtracks, and specific evidence-backed findings.

## Inspiration & Identity
A slightly mischievous, brutally honest testing environment. The "saboteur/gremlin" theme frames the tool as an adversarial test of user experience.

## Why This Matters to the Learner
To build a fully functional, deployable proof-of-concept for the Build With AI: Basics hackathon and deeply understand the mechanics of combining agentic reasoning with browser automation (Playwright).

## What "Working" Looks Like
For the demo, a user enters a demo website URL, sets a task (e.g., "Sign up for the cheapest plan"), and selects the "😈 Impatient User" persona. The system opens a Chromium browser and the user watches live as the AI navigates, clicks, gets confused, backtracks, and finally completes the task. It ends by outputting a Sabotage Report highlighting a critical UX issue with specific evidence from the session.

## The POC Boundary
- One website, one task per run.
- Three predefined personas (e.g., Impatient, Confused, Skeptical).
- Real Chromium browser (Playwright) taking real actions (click, type, scroll, back).
- Basic friction detection (confusion, backtracks).
- Output: Sabotage Report and timeline replay.

## Later
Multiple simultaneous agents, continuous CI/CD testing integration, AI recommendations for fixes, automatic A/B testing, and real user comparison.

## Explicitly Cut
- Full browser automation capable of handling every possible edge-case website (too large for MVP).
- Perfect, scientifically validated UX scoring algorithm (we'll use a diagnostic heuristic).
- Mobile device farms or multi-browser support (we'll stick to Chromium).
- Complex user authentication, databases, or enterprise team features.
