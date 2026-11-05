---
name: MARK VII Tactical HUD
colors:
  surface: '#10141a'
  surface-dim: '#10141a'
  surface-bright: '#353940'
  surface-container-lowest: '#0a0e14'
  surface-container-low: '#181c22'
  surface-container: '#1c2026'
  surface-container-high: '#262a31'
  surface-container-highest: '#31353c'
  on-surface: '#dfe2eb'
  on-surface-variant: '#bac9cc'
  inverse-surface: '#dfe2eb'
  inverse-on-surface: '#2d3137'
  outline: '#849396'
  outline-variant: '#3b494c'
  surface-tint: '#00daf3'
  primary: '#c3f5ff'
  on-primary: '#00363d'
  primary-container: '#00e5ff'
  on-primary-container: '#00626e'
  inverse-primary: '#006875'
  secondary: '#f5fff4'
  on-secondary: '#00391e'
  secondary-container: '#1fff9b'
  on-secondary-container: '#007241'
  tertiary: '#ffeacc'
  on-tertiary: '#422c00'
  tertiary-container: '#ffc863'
  on-tertiary-container: '#765300'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#9cf0ff'
  primary-fixed-dim: '#00daf3'
  on-primary-fixed: '#001f24'
  on-primary-fixed-variant: '#004f58'
  secondary-fixed: '#58ffa5'
  secondary-fixed-dim: '#00e388'
  on-secondary-fixed: '#00210f'
  on-secondary-fixed-variant: '#00522e'
  tertiary-fixed: '#ffdea9'
  tertiary-fixed-dim: '#ffba27'
  on-tertiary-fixed: '#271900'
  on-tertiary-fixed-variant: '#5e4100'
  background: '#10141a'
  on-background: '#dfe2eb'
  surface-variant: '#31353c'
typography:
  headline-xl:
    fontFamily: Geist
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 34px
    letterSpacing: 0.08em
  headline-lg:
    fontFamily: Geist
    fontSize: 20px
    fontWeight: '700'
    lineHeight: 26px
    letterSpacing: 0.06em
  headline-md:
    fontFamily: Geist
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 22px
    letterSpacing: 0.05em
  headline-sm:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 18px
    letterSpacing: 0.05em
  body-lg:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0.01em
  body-md:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0.01em
  body-sm:
    fontFamily: Geist
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.01em
  telemetry-lg:
    fontFamily: JetBrains Mono
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 22px
    letterSpacing: 0.02em
  telemetry-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  telemetry-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.04em
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 9px
    fontWeight: '700'
    lineHeight: 12px
    letterSpacing: 0.12em
spacing:
  gutter: 0.75rem
  margin: 1rem
  space-xs: 0.25rem
  space-sm: 0.375rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system embodies the high-performance aerospace computing aesthetic of an advanced autonomous combat and operational AI. It is strictly engineered as a Windows 11 desktop tactical interface operating at native 1440x900 resolution. The core personality is hyper-intelligent, authoritative, diagnostic, and instant. 

Drawing from military-spec heads-up displays (HUD), advanced telemetry arrays, and Stark Industries avionics, the design language abandons decorative consumer software trends in favor of precise functional instrumentation. Surfaces feature micro-borders, laser-etched crosshairs, fine coordinate ticks, status nodes, and real-time biometric or audio waveforms. Emojis, rounded organic novelties, and casual illustrations are entirely forbidden; iconography is limited to standardized military/avionics geometric vectors, SVG glyphs, and dynamic data visualizations. Visual feedback must feel instantaneous and mission-critical, relying on photonic glows, crisp edge luminescence, and calibrated scanning pulses.

## Colors

The palette is engineered around photon emission on an absolute dark-spectrum canvas, prioritizing high contrast, instant peripheral perception, and low optical fatigue during extended surveillance operations.

### Core Canvas & Structure
- **Deep Obsidian Slate (`#0A0E14`)**: Base canvas, window frame, and void background.
- **Card / Pod Elevation Surface (`#111722`)**: Ground layer for diagnostic pods, telemetry modules, and telemetry panels.
- **Structural Card Highlights (`#1E293B`)**: Crisp dividing grid lines and structural module borders.
- **Secondary Grid & Panel Edges (`#162232`)**: Subtle internal subdivisions, chart reticles, and table dividers.

### Optical Spectral Accents
- **Arc Reactor Electric Cyan (`#00E5FF`) [Primary]**: Primary operational frequency. Used for active HUD reticles, focal system telemetry, AI voice resonance peaks, primary CTA states, and active interactive borders.
- **Electric Cyan Glow (`rgba(0, 229, 255, 0.4)`)**: Photonic halo applied to interactive active nodes, dials, and focused hardware feeds.
- **Avionics Emerald (`#00FF99`) [Secondary]**: Nominal operations, active audio input streams, successful tool call execution pipelines, and neural network parity checks.
- **Telemetry Amber (`#FFB703`) [Tertiary]**: Computation queue throttling, thermal overload thresholds, memory saturation, and awaiting clearance verification.
- **Tactical Crimson (`#FF3366`)**: Muted audio input, interrupted reasoning chains, hostile network vectors, hardware telemetry faults, and manual overrides.
- **Monochrome Data Dim (`#64748B`)**: Passive metric labels, secondary coordinates, and de-emphasized log indices.

## Typography

Typography functions as visual instrumentation. The hierarchy splits strictly between structural administrative commands and dynamic tactical data readouts.

- **Headlines & Interface Labels (`Geist`)**: Rendered in uppercase with disciplined letter spacing (`0.05em` to `0.08em`). Every header acts as an avionics compartment identifier. Line heights are tightly managed to maximize information density without vertical spill.
- **Monospace Telemetry (`JetBrains Mono`)**: Mandated for all numerical data, micro-metrics, hardware clocks, latency meters, AI token streams, audio decibel meters, tool execution outputs, and chronological event logs. Monospace alignment guarantees that flickering real-time values never produce layout shift or jitter.
- **Casing Rules**: Primary module headings and functional indicators are uppercase by convention (`SYS.DIAGNOSTICS // V7.02`). AI conversational discourse output maintains standard sentence casing for rapid visual comprehension.

## Layout & Spacing

Optimized for a 1440x900 native Windows 11 application footprint, the layout operates on a modular HUD cockpit architecture. The screen is locked into an edge-to-edge tactical matrix consisting of a 12-column rigid fluid grid with `0.75rem` (12px) gutters and a calibrated `1rem` (16px) perimeter clearance margin.

### Cockpit Layout Zones
1. **Header Command Bar (40px fixed)**: Top edge system telemetry, timecode (UTC/Zulu), network ping, audio hardware index, Windows title bar controls.
2. **Left Telemetry Flank (3 Columns)**: Real-time neural engine loads, memory bandwidth, thermal tracking, and active peripheral sensor diagnostics.
3. **Center Tactical Core (6 Columns)**: Concentric audio reactor visualizer, live voice spectrogram/waveform, primary AI query terminal, and current execution pipeline.
4. **Right Tool Execution Bay (3 Columns)**: Monospace action stream, automated subroutines, API integration hooks, and contextual sensor feeds.
5. **Bottom Status Strip (28px fixed)**: Diagnostic status flags, global mute toggles, sub-thread telemetry.

Spacing rhythm follows compact 4px base increments (`space-xs` = 4px, `space-sm` = 6px, `space-md` = 12px, `space-lg` = 16px, `space-xl` = 24px) to preserve military telemetry density without structural congestion.

## Elevation & Depth

Depth in this design system is engineered via optical luminance layering, razor-sharp 1px boundary highlights, and planar transparency, abandoning traditional blurry drop shadows.

- **Surface Tiers**:
  - **Void Ground (`#0A0E14`)**: Absolute rear space with low-opacity (2%) vector grid overlays (24x24px cells) representing HUD orientation coordinates.
  - **Module Panels (`#111722` at 85% opacity with 12px backdrop blur)**: Semi-translucent panels revealing coordinate grid scanlines beneath.
  - **Focal Overlays (`#162232` at 95% opacity)**: Transient confirmation layers, diagnostic deep dives, or critical warnings.
- **Boundary Illumination**:
  - Module containers feature a 1px solid border (`#162232`), elevated to `#1E293B` on hover or standard activity.
  - Active focused modules feature a 1px highlight border in `#00E5FF` coupled with an exterior optical glow: `box-shadow: 0 0 12px rgba(0, 229, 255, 0.35), inset 0 0 6px rgba(0, 229, 255, 0.15)`.
- **Scanline Layer**: A subtle horizontal scanline texture (1px scanline every 3px at 4% opacity) runs globally across the viewport to create the tactile sensation of a collimated HUD projector screen.

## Shapes

The geometric architecture is uncompromisingly industrial and sharp (`roundedness: 0`). Curved, organic, or pill-shaped geometries contradict the mil-spec telemetry aesthetic.

- **Edges & Corners**: Every button, input field, panel, and diagnostic box utilizes absolute right angles (0px radius) or 45-degree chamfered technical corners (`clip-path: polygon(...)`).
- **Corner Brackets**: Important panels feature 4px by 4px high-contrast structural tick marks or L-shaped reticle brackets at each corner rendered in `#00E5FF` or `#1E293B`.
- **Dials & Rings**: Concentric diagnostic rings, voice waveform orbits, and audio processing rings are pure geometric circles with crisp 1px strokes, broken up into segmented tick rings (e.g., 60-second or 100-percentile tick marks).

## Components

### Buttons & Tactical Triggers
- **Primary Action (Engage/Trigger)**: 0px border radius, background in `#00E5FF` with text in `#0A0E14` (Geist 12px Bold, uppercase). Subtle hover shifts to `#00FF99` with a distinct `0 0 14px rgba(0, 255, 153, 0.4)` photonic flare.
- **Secondary / Ghost Trigger**: Background in `#111722`, 1px border in `#1E293B`, text in `#00E5FF`. Hover transitions the border to `#00E5FF` with a micro-inset glow.
- **Emergency / Disrupt**: 1px border in `#FF3366`, background in `rgba(255, 51, 102, 0.08)`, text in `#FF3366`. Rapid pulsing glow under warning triggers.

### Diagnostic Cards & Pods
- **Structure**: Encased in `#111722` with a 1px `#162232` frame. 
- **Header Plate**: Integrated 20px header strip containing an uppercase category tag (e.g., `// TELEMETRY: AUDIO_IN`) in `label-caps` (`#64748B`), paired with a pulsing nominal node (`#00FF99` 4x4px dot).
- **Decorators**: Technical crosshairs (`+`) rendered in fine 1px strokes at upper-right coordinate junctures.

### Chips & Status Nodes
- **Format**: Flat, rectangular badges with a 1px stroke. 
- **States**:
  - `NOMINAL`: Text `#00FF99`, border `rgba(0, 255, 153, 0.3)`, background `rgba(0, 255, 153, 0.05)`.
  - `PROCESSING`: Text `#FFB703`, border `rgba(255, 183, 3, 0.3)`, background `rgba(255, 183, 3, 0.05)`.
  - `MUTED / FAULT`: Text `#FF3366`, border `rgba(255, 51, 102, 0.3)`, background `rgba(255, 51, 102, 0.05)`.

### Inputs & Terminal Console Fields
- **Container**: Background `#0A0E14`, 1px border in `#1E293B`.
- **Text & Caret**: Font is `JetBrains Mono` 12px in `#00E5FF`. The caret is a solid blinking cyan block (`|` or full block `█`).
- **Focus**: Border flashes to `#00E5FF` with `box-shadow: 0 0 8px rgba(0, 229, 255, 0.3)`.

### Telemetry Lists & Execution Logs
- **Structure**: Dense tabular lists without alternating zebra stripes. Items are separated by 1px horizontal lines in `#162232`.
- **Format**: Left-aligned UTC timestamp (`HH:MM:SS.ms`) in `#64748B`, followed by system execution code (e.g., `[EXEC_TOOL: WEATHER_RADAR]`) in `#00E5FF`, followed by payload return status in `#00FF99`.

### Specialized HUD Instrumentation
- **Audio Waveform Visualizer**: Real-time vertical frequency bars (2px width, 1px gap) positioned in the central module. Nominal speech peaks render in `#00E5FF`; amplitude overload transitions to `#FF3366`.
- **Arc Reactor HUD Reticle**: Central multi-ringed vector asset. Features outer segmented spinning ticks (indicative of background LLM inference latency) and an inner pulsing core that responds directly to the user's micro-decibel audio input.