# Kid Panel

A small Home Assistant integration that gives someone a control page **without
giving them a Home Assistant login**.

Home Assistant has no per-user permissions: any account, admin or not, can see
and control every entity through the app or the API, whatever its dashboard
shows. Kid Panel sidesteps that. The person gets a link to a simple page; the
page's server side decides what they may see and do, and they never hold a
token that works anywhere else.

## What a panel can do

- **Control** the lights, switches, fans, input booleans, media players,
  scenes and scripts you choose, with a fixed set of actions per type (toggle,
  brightness, play/pause, volume, run).
- **Show read-only values** for any entities you choose. A list in an entity's
  `apps` attribute (for example a screen-time sensor) is shown as a table.
- **Drive a TV** through a `remote` entity with a fixed d-pad: arrows, OK,
  back, home, rewind and fast-forward.

Nothing else is reachable. Requests that name another entity, another action,
a service, extra service data or a template are refused before Home Assistant
sees them.

## How it is reached

Each panel lives at `/kid_panel/<access key>` on Home Assistant's own web
server, so it works wherever Home Assistant does, including through Home
Assistant Cloud remote access. Open it on the phone and choose **Add to Home
screen**.

The key is a 256-bit random value and acts as the password. Wrong keys count as
failed logins, so Home Assistant's IP banning applies when it is enabled.
Requests are capped at 120 per minute per panel. If a link leaks, open the
panel's **Configure** and tick **Generate a new address**.

## Setup

1. Install through HACS (custom repository, type *Integration*), then restart.
2. **Settings → Devices & services → Add integration → Kid Panel**, and name it.
3. Open **Configure** on the new entry, choose what it controls and shows, and
   copy the address shown at the top.

Display names go one per line as `entity_id: Name`.

## Limits

- The panel shows current values only; it has no history.
- The page polls every few seconds while it is open.
- Anyone holding the link has the panel's access, the same as a password would.
