# Teams Class Auto-Join

Logs into Microsoft Teams through the UniPi SSO, opens the class meeting for today, and joins with mic and camera off.

## Setup

```powershell
pip install playwright python-dotenv pyautogui
python -m playwright install chromium
```

`pyautogui` is optional. It dismisses the browser's "Open Microsoft Teams?" popup.

Create a `.env` file next to the script:

```
SSO_EMAIL=youremail@unipi.gr
SSO_USER=
SSO_PASS=yourpassword
```

Leave `SSO_USER` empty to use the part of your email before the `@`.

Edit `classes.json` with your classes:

```json
{ "name": "Network Security", "day": "Thu", "start": "20:00", "url": "https://teams.microsoft.com/l/meetup-join/..." }
```

`day` is Mon, Tue, Wed, Thu, Fri, Sat or Sun. `start` is 24h time.

## Usage

```powershell
python auto_login.py              # today's class (closest to now)
python auto_login.py "Network"    # class whose name contains "Network"
```

The first run signs you in and saves the session in `browser_profile/`. Later runs skip the login.

## Scheduling (Windows)

One Task Scheduler task per class, a few minutes before it starts:

```powershell
schtasks /create /tn "Class-Net" /tr "python E:\path\to\auto_login.py" /sc weekly /d THU /st 19:55
```

If Task Scheduler can't find Python, use the full path to `python.exe`.

## Troubleshooting

- If it can't join, it saves `debug_join.png` and prints the visible buttons. Use those to fix the selectors.
- If the mic stays on, check the mic selectors in `turn_off_prejoin` and `ensure_muted_in_call`.
- If the meeting hasn't been opened by the lecturer, Teams shows a lobby and the script waits.

## Security

Keep these out of git (add to `.gitignore`):

```
.env
browser_profile/
debug_*.png
```

`browser_profile/` contains your logged-in session. Treat it like a password.
