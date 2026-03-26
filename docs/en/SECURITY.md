# Security policy

**UMI-Dex** is a ROS 2 dexterous-hand teleoperation data stack maintained by **Linkerbot**. This project is licensed under [Apache 2.0](../../LICENSE).

**Other locales:** [documentation hub](../README.md)

---

## Supported versions

| Version | Supported | Notes |
|---------|-----------|-------|
| **v1.0.0** | Yes | Tested on **ROS 2 Jazzy** |

Older or unreleased versions may not receive security updates. Use the latest supported release when possible.

---

## How to report a vulnerability

**Do not** report security issues via public GitHub Issues, Discussions, or Pull Requests, so details are not exposed before a fix is available.

**Please report security issues privately by email:**

**[helloworld@linkerbot.cn](mailto:helloworld@linkerbot.cn)**

Include `[SECURITY]` in the subject line so we can prioritize it.

---

## What to include in your report

To help us assess and fix the issue, please include where possible:

1. **Description** — What the issue is and where it occurs (component, file, or node if known).
2. **Impact** — Potential effects (e.g. data exposure, device control, denial of service).
3. **Steps to reproduce** — Minimal steps or a safe proof of concept you can share.
4. **Environment** — OS, ROS 2 distro (e.g. Jazzy), UMI-Dex version, and relevant hardware.
5. **Contact** — How we can follow up (email is enough).
6. **Disclosure preferences** — Any timing requirements for coordinated disclosure.

---

## Response-time expectations

These are **targets**, not guarantees; severity and complexity may change the timeline.

| Stage | Target |
|-------|--------|
| **Initial acknowledgment** | Within **5 business days** |
| **Progress updates** | Regular updates during investigation; if still open, at least about **every 14 days** |
| **Fix and advisory** | Depends on severity; we aim to ship fixes and coordinate disclosure when ready |

If you do not receive an acknowledgment within that window, send one polite follow-up to the same address.

---

## Disclosure policy

1. **Coordinate privately** — Where feasible, we work with you non-publicly until a fix or mitigation is available.
2. **Coordinated disclosure** — Unless required by law or urgent for user safety, please avoid public disclosure before we have reasonable time to address the issue.
3. **Credit** — With your consent, we may credit you in release notes or advisories.
4. **Out of scope** — Issues in third-party dependencies may be forwarded upstream; we will still acknowledge receipt.

---

## Scope

Security review and response under this policy covers components of the UMI-Dex stack in this repository, for example:

| Area | Examples |
|------|----------|
| **ROS 2 nodes** | Node logic, parameters, topics/services/actions, launch and bringup affecting runtime. |
| **Serial I/O** | Serial interfaces and data handling for the hand, controller, or related devices. |
| **Data scripts** | Scripts and pipelines that record or export teleop/sensor data. |

**Typically out of scope** for this project’s process (you may still email for routing): third-party ROS packages unrelated to our patches, purely physical tampering assumptions, and issues only in upstream ROS 2 or the OS—unless they interact with our code in a clearly exploitable way.

---

## Contact

**Security:** [helloworld@linkerbot.cn](mailto:helloworld@linkerbot.cn)  
**Project:** UMI-Dex — Linkerbot

---

*Last updated: March 2026*
