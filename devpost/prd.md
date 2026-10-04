---
doc: prd
status: approved
---

# UXGremlin — Product Requirements

An autonomous AI agent that behaves like a difficult user to test a website's UX and report on friction points. (Source: `scope.md > The Unique Kernel`)

## The Core Journey
1. **Setup:** The user opens the app and sees the Launchpad form. They enter a target website URL, describe a specific task (e.g., "Sign up for the cheapest plan"), and select a "Saboteur Persona" (e.g., 😈 Impatient User).
2. **Launch:** The user clicks "SABOTAGE WEBSITE".
3. **Observation (Live Dashboard):** The UI transitions to the Live Attack Dashboard. The user watches a split-screen: the left side (65-70% of the screen) shows the live Chromium browser interacting with the site. The right side displays a streaming log of the AI's internal reasoning loop (Observe → Understand → Decide → Act).
4. **Conclusion:** The AI either completes the task or gets irreparably stuck and aborts.
5. **The Report:** The system generates a Sabotage Report containing an overall Friction Score, a list of critical UX issues found, and an interactive slideshow replay of the session.

## Screens and Layout
1. **Launchpad (Home):** Clean centered form for URL, Task, and Persona selection.
2. **Live Attack Dashboard:** 
   - **Top Bar:** Current URL, Task, and Agent Status.
   - **Left Pane (65-70%):** Live streaming view of the automated Chromium browser.
   - **Right Pane (30-35%):** "Agent Brain" feed scrolling through thoughts and decisions in real time.
3. **Sabotage Report:** 
   - **Header:** Final Status (Completed / Aborted) and UX Friction Score.
   - **Left Column:** Interactive slideshow player showing screenshots step-by-step.
   - **Right Column:** Breakdown of backtracks, confusion events, and specific evidence-backed recommendations linked to the slides.

## Look and Feel
Clean SaaS aesthetics mixed with a mischievous edge. A sleek dark mode foundation with sharp, vibrant/neon accents (like a toxic green or electric purple) to fit the "gremlin" theme. (Source: `scope.md > Inspiration & Identity`)

## Features and Behavior

### The Sabotage Engine (Backend/Agent)
- **Action Execution:** Instructs a Playwright browser to click, type, scroll, or navigate back.
- **Friction Detection:** Monitors for "confusion events" (AI doesn't know what to do next) or "backtracks" (AI clicks back because a path was wrong).
- **Heuristic Scoring:** Calculates a basic diagnostic friction score based on the number of actions, backtracks, and confusion events relative to the task size.

### Interactive Slideshow Replay (Frontend)
- **Step-by-Step Viewer:** Users can click "Next" and "Previous" to walk through the session.
- **Context Pairing:** Each slide displays the screenshot at that moment paired with what the AI decided to do (e.g., "Decided: I'm not sure which option relates to booking, trying the secondary button").

## States and Boundaries

- **Normal Use (Success):** The AI completes the task, generates a positive/moderate friction score, and produces the report.
- **Task Failure (Stuck/Abort):** If the AI gets completely stuck, loops, or cannot figure out the next step within a reasonable action limit, it aborts the mission. It then generates a Sabotage Report explicitly highlighting the failure and *why* it gave up (e.g., "Abandoned path due to navigation friction").
- **Data Persistence:** For this MVP, session data only lives in memory/local storage while the app is running. Refreshing clears the session.

## Product Decisions
- **Live Feed Layout:** 65-70% browser / 30-35% AI thoughts. *Reason:* Prioritizes the visual impact of seeing the website actually being manipulated, which is the core "wow" factor of the demo.
- **Replay Format:** Interactive Slideshow. *Reason:* Much easier to build and debug than generating a contiguous video file, while actually providing a *better* UX for analyzing specific friction moments step-by-step.
- **Timeout Behavior:** Hard abort and report. *Reason:* Realistic representation of user abandonment.

## What We're Building
- React Frontend (Launchpad, Live Dashboard, Sabotage Report).
- Python/FastAPI Backend.
- Playwright Browser Controller.
- AI Agent Loop (Vision model integration for screenshot analysis and decision making).

## Deferred From the POC
- Persistent database storage of past sabotage reports.
- User accounts / Authentication.
- Concurrent agent runs.

## Non-Goals
- Testing visual CSS regressions.
- Automatically writing code to fix the website's bugs.
