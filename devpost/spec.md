---
doc: spec
status: approved
---

# UXGremlin — Technical Spec

## How This Works, In Plain Language
The system has two main parts: a React frontend where you set up the test and watch it happen, and a Python backend that controls a real browser. When you start a test, the frontend asks the backend to launch a Chromium browser using a tool called Playwright. The backend takes screenshots of the browser, sends them to a vision AI model (via Groq), and asks "what should the user do next?". The AI replies with an action (like click or type), the backend executes it in the browser, and the loop repeats. Meanwhile, the backend streams the browser's screenshots and the AI's thoughts back to the frontend so you can watch it live. When it finishes or gets stuck, it hands the whole timeline back as a Sabotage Report.

## The Core Journey Through the System
1. The user fills out the form on the React Launchpad (URL, task, persona) and hits start. (Implements `prd.md > The Core Journey`)
2. The React app sends a POST request to the FastAPI backend.
3. FastAPI spawns a Playwright Chromium instance, navigates to the URL, and enters the "Agent Loop".
4. Inside the loop, Playwright captures a screenshot and DOM state, and sends it to the Groq API (Qwen Vision).
5. Groq returns a JSON decision (Action, Target, Thought).
6. FastAPI executes the action via Playwright and sends a Server-Sent Event (SSE) or WebSocket update to the React frontend with the new screenshot and the AI's thought.
7. The React frontend updates the split-screen UI live.
8. When the task is done or aborted, FastAPI returns the final Sabotage Report JSON.
9. React displays the report and the interactive slideshow.

## Stack
- **Frontend**: React (Vite SPA) with TypeScript and Tailwind CSS. (Simple, fast, no SSR needed for a dashboard).
- **Backend**: Python with FastAPI. (Great for async streaming and integrating tightly with Playwright).
- **Browser Automation**: Playwright for Python.
- **AI Model**: Groq API (e.g. Qwen Vision models or similar supported vision models) for extremely fast inference.

## Where It Runs and How Someone Tries It
For the MVP and hackathon demo video, this will run locally.
- **Frontend**: Run `npm run dev` (starts on localhost:5173).
- **Backend**: Run `uvicorn main:app --reload` (starts on localhost:8000).
- **Prerequisites**: Playwright requires a local browser installation (`playwright install chromium`). The backend requires a `.env` file with `GROQ_API_KEY`.
- Deployment to the web (e.g., Vercel + Render) is optional and can be handled later.

## Look and Feel
Clean SaaS aesthetics mixed with a mischievous edge. Sleek dark mode foundation with toxic green/neon accents. Implemented via Tailwind CSS utility classes.

## Components

### React Frontend (Vite)
- **Launchpad Component**: Form state management for URL, task, persona.
- **LiveDashboard Component**: Manages WebSocket/SSE connection to display live screenshots (left pane) and streaming thoughts (right pane).
- **Report Component**: Renders the final friction score and the interactive slideshow player using local state.

### FastAPI Backend
- **Browser Manager**: Wraps Playwright to launch, navigate, and interact with the DOM.
- **Agent Loop**: The while-loop that orchestrates capture -> Groq inference -> execute -> stream update.
- **Reporter**: Generates the final Sabotage Report JSON from the collected session data.

## Data Model
Session data is ephemeral and stored in memory on the backend during the run, then passed to the frontend for the report.
- `Session`: `{ id, url, task, persona, status, friction_score, actions: [], issues: [] }`
- `Action`: `{ step_number, screenshot_base64, thought, action_taken }`

## File Structure
```
uxgremlin/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Launchpad.tsx
│   │   │   ├── LiveDashboard.tsx
│   │   │   └── Report.tsx
│   │   ├── App.tsx
│   │   └── index.css
│   ├── package.json
│   └── vite.config.ts
├── backend/
│   ├── agent.py         # AI interaction logic
│   ├── browser.py       # Playwright wrapper
│   ├── main.py          # FastAPI server and endpoints
│   └── requirements.txt
└── devpost/             # Planning docs
```

## External Services and Dependencies
- **Groq API**: Used for Vision LLM inference. Requires API key. Documentation: https://console.groq.com/docs/quickstart.

## Important Failure Modes
- **Website blocks automated browser**: Playwright gets stuck on a Cloudflare captcha. -> Agent aborts gracefully and generates a report stating "Blocked by bot protection".
- **Groq API Rate Limit/Timeout**: -> Agent aborts gracefully, showing an API error on the frontend.

## What Was Simplified and Why
- **Interactive Slideshow instead of Video Generation**: Generating a continuous mp4 video on the backend is complex and resource-heavy. Passing an array of base64 screenshots and letting the frontend render them as a slideshow is much simpler and achieves the exact same user value (actually better for stepping through).
- **In-Memory Sessions**: No database setup required. Faster to build, perfectly fine for a local PoC demo.

## Decisions and Open Issues
- **Decision**: Vite React SPA instead of Next.js to simplify architecture for a single-page dashboard experience.
- **Decision**: Used Groq for vision model based on learner preference for speed and the free tier.
- **Learner Uncertainty**: The learner explicitly stated they had no major uncertainties right now and are comfortable with the plan.
