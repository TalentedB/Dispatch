# Dispatch UI redesign

Full app redesign on `codex/ui-redesign`, in an independent GitHub clone. The
original checkout and its solver work were not edited.

## Preserved

The competition specifies grid-aligned travel at one block per minute, job
locking, job chaining, and interruptible returns. The checker and trace tests
remain the authority for replay correctness. The JSON contract, exporter,
sampling engine, algorithm registrations, view registrations, overlay
registrations and playback driver retain their existing responsibilities.

All scenario, upload, algorithm, view, overlay, speed, seek, split-mode, inspector
and keyboard actions remain available. Labels and metrics derive from existing
traces. No product metrics, photographs, testimonials or logos were invented.
The existing locally bundled Geist font is retained in the Coral app palette.

## Changes

Light paper surfaces, a quiet top bar, a map-led workspace, ruled inspector rows,
larger status figures and clearer transport replace the dark gradient/glow
presentation. Algorithm actions appear before detailed metrics. Mobile controls
have 44px touch targets and the inspector opens over the workspace; playback
remains accessible. Terrain uses a restrained sage-to-clay coverage scale.

Decorative SVG pulses, the base glow and flashing WebGL lights were removed.
The scalar scrubber now creates a single thumb and accepts number or array
callback values safely. Playback shortcuts yield to focused controls and menus.

## Verification

- TypeScript and production Vite build pass under Node 24.
- 172 solver, checker and trace-export tests pass without changes to tests.
- 14 browser smoke checks pass: playback, steps, keyboard, scrubbing, speed,
  algorithm selection, layers, three views, split mode, inspector tabs, width
  checks from 320 to 1920px, mobile inspector and native trace upload.
- Hallmark final static and rendered sweep: 0 Floor failures, 0 Reflex findings,
  0 warnings, 2 dismissed image-slot checks. These checks mistake shadcn's
  `data-slot` controls for image slots; they are actual controls, not images.
- The initial full Python run also encountered three pre-existing Windows
  benchmark failures and a temp-directory permission error. The benchmark
  tests expect POSIX path/process behavior. They were not altered for this UI.
- Lint exits successfully with existing React/Three/shadcn warnings. The
  production bundle still has Vite's large-chunk warning for the eager 3D stack.

The wiring inventory retains 28 handlers verbatim and records the changed
scrubber handler. The retained scalar-or-array callback is exercised in browser
checks. Three generated Base UI input identities change when controls move;
semantic control behavior is verified. Two alleged links were SVG animation
`from`/`to` values, not navigation. The original unmodified baseline inventory is
saved locally as `before-original.json`; comparison paths and the baseline port
were normalized to point to this clone's equivalent source and route.

Hallmark's installed scripts have Windows CRLF assumptions, so a local ignored
copy normalizes newlines. The acknowledgement parser in that copy was adjusted
to accept an arithmetic asterisk in the removed SVG endpoint value. No app
validation rules, tests or baseline values were loosened to achieve the result.

The before/after visual comparison is available locally at `.hallmark/compare.html`.
Final screenshots are in `.hallmark/shots/` and `.hallmark/preview/`.
There are no missing photo or content slots. A larger real scenario trace with
standby relocation would best demonstrate that existing contract capability.

## Finish review

An independent Hallmark reviewer raised phone touch-target sizing and desktop
comparison action visibility. Both were addressed. A follow-up caught a
specificity override on the phone view switcher; the mobile segmented-control
rule now explicitly sets 44px height. The final browser geometry check measures
these targets rather than relying on screenshot appearance.

Baseline capture limitation: the saved original-UI screenshots show the full original interface, but its snapshot server rejected the bundled font path. They use a fallback face. Two font-correct recapture attempts timed out. The redesigned UI's font loaded and its final render checks passed; the comparison is reliable for layout and controls, not exact original typography.
