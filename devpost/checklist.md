---
doc: checklist
status: approved
---

# Build Checklist

Build mode: fast

## Slices

- [x] **1. Frontend scaffold and Launchpad form**
  Becomes usable: The React frontend runs and shows the dark/neon styled Launchpad form where a user can enter URL, task, and persona.
  Why now: Proves the React setup and establishes the entry point of the app.
  PRD ref: `prd.md > The Core Journey` (step 1)
  Spec ref: `spec.md > Components`, `spec.md > File Structure`
  Build: Initialize Vite React app in `frontend/`, configure Tailwind CSS, build the Launchpad component with dark/neon theme, and show form state.
  Verify (mechanical): Start `npm run dev` in `frontend/`, open browser, fill out form.
  Learner check: Start the frontend server, open the app, and confirm the Launchpad form looks like a sleek, mischievous SaaS tool.
  Commit: `Scaffold frontend and Launchpad form`

- [x] **2. Backend scaffold and Playwright connection**
  Becomes usable: FastAPI backend receives a request from the Launchpad, starts a Playwright browser locally, and navigates to the URL.
  Why now: Connects frontend to backend and proves the core browser automation capability without AI yet.
  PRD ref: `prd.md > The Core Journey` (step 2)
  Spec ref: `spec.md > FastAPI Backend`, `spec.md > File Structure`
  Build: Setup `backend/` with FastAPI and Playwright, create a POST endpoint to receive Launchpad data, launch Chromium, navigate to the URL, and return success.
  Verify (mechanical): Start FastAPI, submit Launchpad form, verify Playwright opens the target URL.
  Learner check: Submit a URL in the Launchpad and confirm a real browser window opens on your machine and goes to that URL.
  Commit: `Connect frontend to FastAPI and launch Playwright`

- [x] **3. Live Dashboard layout and basic streaming**
  Becomes usable: The UI transitions to the Live Dashboard, showing a placeholder for the browser view and receiving simulated live text updates from the backend.
  Why now: Proves the streaming connection (WebSocket or SSE) before adding the complexity of the AI loop.
  PRD ref: `prd.md > The Core Journey` (step 3), `prd.md > Screens and Layout`
  Spec ref: `spec.md > Components` (LiveDashboard), `spec.md > The Core Journey Through the System`
  Build: Build the split-screen LiveDashboard in React. Add a mock loop in FastAPI that streams text updates back to React via SSE/WebSocket.
  Verify (mechanical): Start both servers, submit form, verify Dashboard shows split screen and receives mock streamed text.
  Learner check: Submit the form and confirm the app transitions to a split-screen dashboard with streaming text appearing on the right.
  Commit: `Add Live Dashboard and mock streaming`

- [x] **4. The Sabotage Engine (Groq Vision Loop)**
  Becomes usable: The backend captures real screenshots of the browser, sends them to Groq Vision API, gets a decision, streams the thought to the frontend, and executes the action.
  Why now: This is the unique kernel. It integrates the AI to make real decisions on the webpage.
  PRD ref: `prd.md > Features and Behavior` (The Sabotage Engine)
  Spec ref: `spec.md > External Services and Dependencies`, `spec.md > The Core Journey Through the System`
  Build: Implement the full `agent.py` loop: screenshot -> Groq API -> parse decision -> send thought to frontend via SSE -> execute in Playwright.
  Verify (mechanical): Provide Groq API key, run a test against a simple site, verify thoughts stream to the frontend and Playwright performs actions.
  Learner check: Add your Groq API key, launch a test on a simple site, and watch the AI's thoughts stream in while the browser clicks around.
  Commit: `Implement Groq vision loop and live action execution`

- [ ] **5. Live Screenshot Streaming**
  Becomes usable: The left pane of the Live Dashboard shows real-time screenshots of what the browser sees.
  Why now: Completes the Live Dashboard experience visually, requiring base64 image streaming alongside the text thoughts.
  PRD ref: `prd.md > The Core Journey` (step 3)
  Spec ref: `spec.md > Components` (LiveDashboard)
  Build: Update the SSE/WebSocket payload to include the base64 screenshot from Playwright, and render it in the LiveDashboard left pane.
  Verify (mechanical): Run a test, verify the LiveDashboard shows updating screenshots.
  Learner check: Run a test and confirm the LiveDashboard now shows the actual website on the left side updating as the agent works.
  Commit: `Stream live screenshots to Dashboard`

- [ ] **6. The Sabotage Report & Slideshow**
  Becomes usable: When the task finishes or aborts, the app shows a summary score and an interactive slideshow of the entire run.
  Why now: Completes the core journey by providing the final output and value to the user.
  PRD ref: `prd.md > The Core Journey` (step 5), `prd.md > Features and Behavior` (Interactive Slideshow Replay)
  Spec ref: `spec.md > Components` (Report), `spec.md > Data Model`
  Build: Calculate basic friction score on backend, return full session history on completion, build the Report component with the slideshow UI.
  Verify (mechanical): Let a task complete/abort, verify the UI transitions to Report and clicking next/prev cycles screenshots and thoughts.
  Learner check: Let a test run until it finishes or aborts, then click through the slideshow report to see the steps.
  Commit: `Add Sabotage Report and interactive slideshow`

## Hands-on Checkpoints

- [ ] Early usable behavior explored — end of Slice 3 (Live Dashboard layout and basic streaming)
- [ ] Final kick-the-tires exploration and feedback completed

## Final Review

- [ ] Final review complete — feedback resolved and learner confirms ready to ship

## Code Tour and App Map

- [ ] Learning activity complete — guided route, focused alternative, prior practice connected, or brief recap
- [ ] Optional edit and transfer reflection addressed — offered/declined/already covered/not applicable as appropriate
- [ ] `devpost/app-map.html` generated from finished code, checked, and shown, including a project-grounded practice to reuse

Activity and evidence: [what actually happened; real document/test/code references; unfinished work if interrupted]
Route and stops: [actual paths and symbols; guided stops completed, or reference-only route]
Edit outcome: [tried/kept/reverted/declined/not applicable; verification if changed]
Reflection: [offered/answered/declined/already covered — personal answer belongs only in the ignored profile]
Activity mode: [live app and editor, explicit static fallback, focused alternative, prior practice, or recap]

## Revisions

- Added 'back' button navigation (to be implemented).
- Improved UI styling for Live Dashboard to match the "sleek, mischievous SaaS tool" vibe (to be implemented).
