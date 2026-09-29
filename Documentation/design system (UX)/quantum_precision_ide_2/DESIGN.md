---
name: Quantum Precision IDE
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#3f4850'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#707881'
  outline-variant: '#bfc7d2'
  surface-tint: '#006398'
  primary: '#006194'
  on-primary: '#ffffff'
  primary-container: '#007bb9'
  on-primary-container: '#fdfcff'
  inverse-primary: '#93ccff'
  secondary: '#0051d5'
  on-secondary: '#ffffff'
  secondary-container: '#316bf3'
  on-secondary-container: '#fefcff'
  tertiary: '#006386'
  on-tertiary: '#ffffff'
  tertiary-container: '#007da8'
  on-tertiary-container: '#fbfcff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#cce5ff'
  primary-fixed-dim: '#93ccff'
  on-primary-fixed: '#001d31'
  on-primary-fixed-variant: '#004b73'
  secondary-fixed: '#dbe1ff'
  secondary-fixed-dim: '#b4c5ff'
  on-secondary-fixed: '#00174b'
  on-secondary-fixed-variant: '#003ea8'
  tertiary-fixed: '#c3e8ff'
  tertiary-fixed-dim: '#78d1ff'
  on-tertiary-fixed: '#001e2c'
  on-tertiary-fixed-variant: '#004c68'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  headline-xl:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-md:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  body-sm:
    fontFamily: Geist
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 16px
  label-lg:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: -0.01em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '400'
    lineHeight: 12px
  code:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 16px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 0.5rem
  margin: 0.75rem
  space-xs: 0.25rem
  space-sm: 0.375rem
  space-md: 0.5rem
  space-lg: 0.75rem
  space-xl: 1rem
---

## Brand & Style

This design system establishes an ultra-rigorous, modern laboratory workbench environment tailored for computational physics and material science exploration. Designed specifically for intensive desktop workflows (such as PyQt6-driven interfaces and Matplotlib-rendered Quantum ESPRESSO datasets), the visual language rejects decorative clutter in favor of high-density clarity, structural alignment, and optical precision.

The design movement combines **Minimalism** with **Modern Scientific Utility**:
- **Aesthetic Core:** Surgical, razor-sharp visual framing using fine boundaries, clean planar layering, and zero-distortion data representation.
- **Tone:** Methodical, reliable, authoritative, and frictionless under prolonged operational sessions.
- **Emotional Response:** Inspires absolute confidence in numerical data, crystalline lattice projections, Brillouin zone paths, and convergence graphs.

## Colors

The palette employs a carefully calibrated tonal spectrum engineered for high legibility under varying ambient laboratory lighting conditions:

- **Primary Surfaces:**
  - Application Canvas / Viewport Backdrop: `#f8fafc` (Slate 50)
  - Active Panels, Data Grids, and Card Containers: `#ffffff` (Pure White)
  - Dock Widgets & Inactive Tab Wells: `#f1f5f9` (Slate 100)
  - Structural Panel Dividers & Borders: `#e2e8f0` (Slate 200) and `#cbd5e1` (Slate 300)

- **Typography & Glyphs:**
  - High-Emphasis / Primary Scalar Labels: `#0f172a` (Slate 900)
  - Secondary Readouts & Navigation: `#334155` (Slate 700)
  - Dimmed Metadata, Units, & Structural Guides: `#64748b` (Slate 500)

- **Chromatics & Interactive Accents:**
  - Focus Ring, Selection Rings & Active Tooltips: `#0284c7` (Electric Scientific Cyan)
  - Primary Action States, Calculated Vectors & Orbitals: `#2563eb` (Precision Cobalt Blue)
  - Live Process Flags & Energy Convergences: `#0099cc` (Instrument Teal-Cyan)

- **Matplotlib Integration:**
  Embedded visualization canvases should adopt a clean `#ffffff` plot frame with `#e2e8f0` major gridlines, `#f1f5f9` minor gridlines, and categorical data curves mapped along Cobalt `#2563eb`, Cyan `#0284c7`, Emerald `#059669`, and Amber `#d97706`.

## Typography

Typography prioritizes information density and monospaced data alignment:

- **Geist** serves as the UI interface typeface, providing geometric neutrality, compact vertical metrics, and optical legibility in narrow inspector trees and sidebar panes.
- **JetBrains Mono** governs all numerical readouts, atomic coordinate matrices, calculation output streams, convergence limits, and tabular axis labels.
- Desktop environments preserve 11px and 12px baselines for maximal spatial economy across multi-panel dock layouts. Tabular figures (`tnum`) must remain enabled across all monospaced numerical contexts to eliminate jitter during real-time solver updates.

## Layout & Spacing

The layout model is anchored by a dense, tile-docked workbench structure typical of technical desktop suites:

- **Multi-Split Dock Grid:** Content panels (3D Crystal Viewer, Matplotlib Convergence Graphs, K-Point Inspector, Job Console) are organized in resizable, splitter-separated dock regions with minimum 1px dividers.
- **Spacing Rhythm:** Based on an uncompromising 4px sub-grid (`0.25rem`). Component paddings stay compressed (`space-xs` through `space-md`) to ensure dense instrument readouts remain entirely visible on 1080p and 4K displays without forced scrolling.
- **Form Factor Rules:**
  - **Desktop / Multi-Monitor (Primary):** Flexible horizontal and vertical split panes with dynamic tool palettes collapsed to 32px icon rails.
  - **Compact Displays / Laptops:** Inspectors and log terminals collapse into single tab-stacked bottom and right drawers.

## Elevation & Depth

Visual hierarchy is maintained without heavy dropped shadows or fuzzy blurs, maximizing clarity for complex charts:

- **Low-Contrast Structural Outlines:** Panels, toolbar groups, and dock headers rely strictly on `1px solid #e2e8f0` or `#cbd5e1` borders to articulate geometric separation.
- **Tonal Layering:**
  - Base Shell Canvas: `#f8fafc`
  - Floating Toolpalettes & Context Menus: `#ffffff` with a disciplined 1px border (`#cbd5e1`) and an ultra-subtle ambient offset (`box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06)`).
  - Active Document / Viewport Layer: Elevated via pure white background (`#ffffff`) sharply contrasted against the inactive well (`#f1f5f9`).
- **Interactive State Depth:** Focused inputs, selected lattice nodes, and active docked tabs assert priority using an interior or outline accent stroke of `#0284c7` (Electric Cyan).

## Shapes

The design system adopts a **Soft (Level 1)** corner radius language:
- Buttons, input controls, chips, and dockable tabs use `0.25rem` (4px) corner radii.
- Modals, tool windows, and floating overlay cards use `0.375rem` (6px) to maintain a crisp, industrial aesthetic that aligns flush against window borders and grid splits.
- Data tables, viewport viewboxes, and split pane frames maintain clean `0px` intersections at pane borders to reinforce structural cohesion.

## Components

- **Buttons:**
  - *Primary:* `#2563eb` fill with `#ffffff` text, 4px radius, 28px height in toolbars, font: `Geist` 12px weight 600. Hover state: `#1d4ed8`.
  - *Secondary / Tool:* Transparent or `#ffffff` surface, 1px `#e2e8f0` border, `#334155` text. Hover: `#f1f5f9` fill, `#0f172a` text.
  - *Icon Actions:* Flat square 28x28px targets, `#64748b` icon stroke, shifting to `#0284c7` on hover.

- **Input Fields & Numeric Spinners:**
  - Height 26px to 28px, background `#ffffff`, border 1px `#cbd5e1`, font: `JetBrains Mono` 11px.
  - Focused state: 1px border `#0284c7` with a matching 1px soft cyan halo (`rgba(2, 132, 199, 0.15)`).
  - Numeric stepper buttons integrated flush to the right edge with subtle horizontal dividing lines.

- **Tabs & Panel Headers:**
  - 30px container height. Inactive tab: `#f1f5f9` surface with `#64748b` typography.
  - Active tab: `#ffffff` surface, `#0f172a` typography, topped with a 2px `#0284c7` indicator line.

- **Data Tables & Inspectors:**
  - Alternating rows using `#ffffff` and `#f8fafc`. Header height 24px in `#f1f5f9` with all-caps 10px monospaced column definitions (`#64748b`).
  - Active cell selection: Subtle `#e0f2fe` highlight with a 1px `#0284c7` bounding stroke.

- **Chips & Status Badges:**
  - Compact 18px height, 3px border radius, font `JetBrains Mono` 10px.
  - Convergence Success: `#f0fdf4` background, `#166534` text, `#bbf7d0` border.
  - Active Calculation: `#f0f9ff` background, `#0369a1` text, `#bae6fd` border.
  - Error / Divergence: `#fef2f2` background, `#991b1b` text, `#fecaca` border.

- **Checkboxes & Radios:**
  - 14x14px bounds, 3px corner radius (checkbox) or circular (radio), `#ffffff` background with 1px `#cbd5e1` outline.
  - Checked: Solid `#0284c7` fill with white `#ffffff` mark.