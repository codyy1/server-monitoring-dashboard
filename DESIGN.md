# DESIGN.md: WSL + VM Server Monitoring Console

## Identity & Character
- **Product**: Linux WSL2 System Telemetry & VirtualBox VM MySQL Monitoring Console (`OS PROJECT`)
- **Tone**: Industrial utilitarian systems telemetry (inspired by hardware rack instrumentation and classic UNIX `htop` / Cockpit readouts)
- **Dials**:
  - **ENERGY**: 1 (Calm, high-density operational clarity)
  - **RHYTHM**: 2 (Structured telemetry readout bands with asymmetric primary host + VM database split)
  - **MOTION**: 1 (Instant state transitions, live canvas sparklines, zero decorative bounce/float)

## Color System (2 Core + 1 Accent + Semantic Status)
- **Surface / Canvas (`--bg-canvas`)**: `#0f1210` (Warm carbon slate)
- **Panel Surface (`--bg-panel`)**: `#171b18` (Elevated instrument bay)
- **Primary Text (`--text-primary`)**: `#ecefe8` (Crisp phosphor bone, 14.8:1 contrast)
- **Secondary Text (`--text-muted`)**: `#9ca69e` (Muted sage grey, 6.2:1 contrast)
- **Accent (`--accent`)**: `#d4882a` (Amber hardware indicator)
- **Status Tokens**:
  - Healthy / Connected: `#3ca86b`
  - Warning: `#d4882a`
  - Critical / Disconnected: `#d64545`

## Decision Log (R-31)
- **Palette**: Warm carbon + amber hardware indicator avoids generic AI blue-purple gradients and maintains >4.5:1 WCAG AA contrast across all readouts.
- **Typography**: System UI sans for scannable labels paired with tabular monospace (`font-variant-numeric: tabular-nums`) strictly for live numeric counters, IPs, PIDs, and SQL latencies so values never jitter during refresh.
- **Layout**: Top hardware status bar (WSL Host + VM MySQL bridge status), primary 2-column split (Real-time `/proc` Linux telemetry vs. VirtualBox VM MySQL storage & connection diagnostics), followed by live process table and historical DB rows.
- **States**: Every data panel implements explicit Loading, Empty, and Error states (especially when the VirtualBox VM MySQL server is offline or unreachable).
