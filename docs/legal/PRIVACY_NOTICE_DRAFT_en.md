# Detect A Clip — Privacy notice (DRAFT FOR COUNSEL)

> **Status: DRAFT_FOR_COUNSEL. Not legally reviewed. Not for production or for any user.**
> Written by the implementing AI from the actual data flows in this repository (2026-10-09)
> so that counsel has an accurate starting point (P05-T01, P06-T07, PRIV-01). The operating
> entity, contact details, audience, regions and lawful bases are unknown (B-04) and are left
> as open fields. Governing-language and translation rules are set by counsel.

## Who we are
[ENTITY NAME, ADDRESS, CONTACT — owner to supply]

## What the app does
When you tap **Start**, the app asks your phone's system for permission to capture your screen
for one scan. It looks at up to about 12 seconds of the video playing in another app on this
phone and compares it with a small catalogue stored on the phone. It then shows a result or
says it could not find a confident match.

## What is processed, where, and for how long
| Data | Where | Kept for |
|---|---|---|
| Screen frames from one scan | Only in this phone's memory | Released during the scan; never saved to a file |
| Visual fingerprints of those frames | Only in this phone's memory | Discarded when the scan ends |
| The result (for example, a catalogue title or "no confident match") | Only in this phone's memory | Until your next scan or 15 minutes, whichever comes first. Closing the app may lose it |
| Your acceptance of these terms (version, language, time) | On this phone | Until you change your choice or uninstall |

Screen content, fingerprints, results and scan timing **are not sent** from the phone in this
version. There are no analytics, advertising or crash-reporting services in the app.
[Counsel: confirm against the final binary, SDK inventory and store labels (REL-01).]

## What the screen may show
Anything visible during the scan could be captured, including notifications, messages or
other people's information if they appear on screen. Stop the scan before opening private
content. [Counsel: assessment of incidental third-party data, DPIA (see DPIA_SCREENING).]

## Your controls
- Each scan needs your tap and the system's permission. The app never captures on launch.
- You can stop capture with the system's screen-sharing control, the notification's Stop
  action (if notifications are allowed) or the in-app Stop. Returning to the app and tapping
  Cancel discards a match still being computed.
- Notifications are optional.

## Children
[Owner/counsel: intended audience and age assessment (D04, S20).]

## Your rights and contact
[Counsel: rights by region; contact route; complaint authority.]

## Changes
If these terms change, including a change only to a translation, the app will show the new
version and ask again before the next scan.
