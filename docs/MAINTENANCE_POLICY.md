# Maintenance Policy

## Current status: single maintainer

ESP32 Multi Flash Manager is currently maintained by one person
([SomangshuDas](https://github.com/SomangshuDas)), in the open, in their
spare time. That means a bus factor of one: if the maintainer becomes
unavailable, unresponsive, or simply stops working on this project,
there is currently no one else with commit/release access to keep it
going. This document exists so that risk is stated plainly rather than
discovered the hard way, and so there's a documented plan for what
happens if it materializes.

## What this means in practice today

- **Response time isn't guaranteed.** Issues and pull requests are
  reviewed as time allows; there's no SLA.
- **Security fixes are best-effort.** As stated in
  [`SECURITY.md`](../SECURITY.md), only the latest tagged release is
  supported, and there's no dedicated security team behind that support.
- **Releases happen when the maintainer has time to cut one**, not on a
  fixed schedule.

## If the maintainer becomes unavailable

If there is no response to issues, pull requests, or the contact
information in `SECURITY.md` for an extended period (as a rule of thumb,
several months with no commits, releases, or maintainer activity of any
kind), the following is the intended path forward, in order:

1. **A visible signal.** Someone who notices the inactivity should open
   a GitHub issue explicitly asking about the project's maintenance
   status, so the silence is documented and discoverable rather than
   just assumed.
2. **Community fork.** Given no response, the recommended path is a
   community fork under a new maintainer or small maintainer group.
   This repository's license (see [`LICENSE`](../LICENSE)) already
   permits this without needing the original maintainer's explicit
   sign-off.
3. **Pointing people to the fork.** If GitHub's repository-transfer
   process or direct contact with the maintainer is possible, the goal
   would be to either transfer this repository to the new
   maintainer(s) or, failing that, get this README updated to point at
   the actively maintained fork so users and search engines land in the
   right place.

## Reducing the risk over time

Concretely, a few things would lower the bus factor below one and are
worth prioritizing as the project grows:

- Documenting the release process precisely enough (see
  [`docs/DEVELOPER_DOCUMENTATION.md`](DEVELOPER_DOCUMENTATION.md) and
  [`docs/BUILD_INSTRUCTIONS.md`](BUILD_INSTRUCTIONS.md)) that a new
  contributor could cut a release without the original maintainer's
  direct involvement.
- Adding a second person with at least triage/write access once a
  trusted, sufficiently active regular contributor emerges.
- Keeping CI (tests, version-consistency checks, release builds) fully
  automated, so as much of the release process as possible doesn't
  depend on tribal knowledge held by one person.

This policy will be revisited if/when a second maintainer joins.
