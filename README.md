# 21 Draw Email Assistant

Monitors Gmail for Gemini meeting notes, parses them with Claude AI, and creates ready-to-send follow-up email drafts for artists.

---

## What it does

After every course production call with an artist, Google Meet's Gemini feature emails you a set of meeting notes. This script:

1. **Watches your inbox** for those Gemini notes emails (from `gemini-notes@google.com`, subject matching `21 Draw Course Production`)
2. **Filters** the subject line with a regex to identify artist calls and skip internal meetings
3. **Sends the notes to Claude** (Anthropic API) to extract structured data: artist name, email, course topic, deadline dates, and action items
4. **Looks up Google Drive** to find the artist's `_artist_edit` upload folder and Course Outline doc (handles pen names vs legal names automatically)
5. **Renders a Jinja2 template** into a polished follow-up email, pre-filled with all the Drive links and deadline dates
6. **Creates a Gmail draft** in the existing email thread with that artist (or starts a new one)
7. **Labels** the source Gemini email as `AutoDraft/Processed` so it won't be picked up again
8. **Notifies via Slack** (optional) with a direct link to review and send the draft

The draft is never sent automatically — you always review and hit Send yourself.

---

## Prerequisites

- **Python 3.12+**
- A **Google Cloud project** with the Gmail API and Google Drive API enabled
- An **OAuth 2.0 Desktop client** credentials file downloaded from Google Cloud Console
- An **Anthropic API key** (Claude access)

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create your `.env` file

Copy the example and fill in the required values:

```bash
cp .env.example .env
```

At minimum you need:

```dotenv
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

See the [Configuration reference](#configuration-reference) below for all available settings.

### 3. Place your OAuth credentials file

Download the OAuth 2.0 Desktop client JSON from [Google Cloud Console](https://console.cloud.google.com/) and save it as:

```
credentials/gmail_credentials.json
```

The `credentials/` directory is git-ignored — never commit this file.

### 4. Authenticate (one-time)

```bash
python run.py --setup-auth
```

This opens a browser window for you to log in with your Google account and grant the required permissions. The token is saved to `credentials/token.json` and auto-refreshes from then on.

**OAuth scopes requested:**
- `gmail.readonly` — read emails and search inbox
- `gmail.compose` — create drafts
- `gmail.modify` — add labels to messages
- `drive.readonly` — look up artist folders and docs in Google Drive

---

## Usage

| Command | Description |
|---|---|
| `python run.py` | Single run: check for new Gemini notes and create any pending drafts |
| `python run.py --dry-run` | Preview mode: find matching emails and print the draft body to console; nothing is created or labelled |
| `python run.py --daemon` | Continuous mode: poll at the configured interval until stopped with Ctrl+C |
| `python run.py --setup-auth` | One-time OAuth setup: opens browser to authenticate your Google account |

### Examples

```bash
# Quick check — see if anything needs processing
python run.py --dry-run

# Process emails for real
python run.py

# Run as a background monitor (every 5 minutes by default)
python run.py --daemon
```

---

## Configuration reference

All settings are loaded from `.env` in the project root. Pydantic validates and type-converts them on startup.

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | **Yes** | — | Anthropic API key for Claude (used to parse meeting notes) |
| `GMAIL_CREDENTIALS_PATH` | No | `credentials/gmail_credentials.json` | Path to the OAuth client secrets file from Google Cloud Console |
| `GMAIL_TOKEN_PATH` | No | `credentials/token.json` | Where to save/load the OAuth access token after authentication |
| `POLLING_INTERVAL_SECONDS` | No | `300` | Seconds between inbox checks when running in `--daemon` mode |
| `GEMINI_SENDER` | No | `gemini-notes@google.com` | Sender address used to identify Gemini notes emails |
| `SUBJECT_PATTERN` | No | See below | Regex applied to the email subject to confirm it's an artist meeting and extract the artist name |
| `DRIVE_BASE_FOLDER` | No | `Ext - 21 Draw/_online_courses` | Shared Drive path where artist course folders live (first segment is the shared drive name) |
| `PROCESSED_LABEL` | No | `AutoDraft/Processed` | Gmail label applied to emails after a draft has been created, to prevent reprocessing |
| `SLACK_WEBHOOK_URL` | No | — | Slack incoming webhook URL; leave unset to disable Slack notifications |

### Default subject pattern

The default regex matches subjects like `Notes: "21 Draw Course Production w/ Marian & ArtistName"` while excluding internal team meetings (Darko, JP, David, etc.):

```
Notes: [""](?=[^""]*Marian)(?![^""]*(?:Darko|Course prod|Beers and Brags|Noras|\bJP\b|Renco|David|Stefan))([^""]+)[""]
```

The first capture group (`group(1)`) is used as the artist name hint when parsing the notes.

---

## Project structure

```
21draw-email-assistant/
│
├── run.py                              # CLI entry point (--setup-auth, --dry-run, --daemon)
├── requirements.txt                    # Python dependencies
├── .env                                # Local config — not committed to git
├── .env.example                        # Template showing available settings
│
├── config/
│   └── templates/
│       └── artist_followup.md          # Jinja2 email template (edit to customise the email)
│
├── credentials/
│   ├── gmail_credentials.json          # OAuth client secrets — download from Google Cloud Console
│   └── token.json                      # OAuth token — auto-generated by --setup-auth
│
└── src/
    └── email_assistant/
        ├── config.py                   # Pydantic settings model (loads from .env)
        ├── main.py                     # EmailAssistant orchestrator — ties everything together
        │
        ├── gmail/
        │   ├── auth.py                 # OAuth2 flow and token management
        │   └── client.py               # Gmail API: search, read, create drafts, manage labels
        │
        ├── drive/
        │   └── client.py               # Google Drive API: find artist folders and docs
        │
        ├── parser/
        │   └── notes_parser.py         # Sends notes to Claude; returns structured MeetingData
        │
        ├── drafts/
        │   ├── generator.py            # Orchestrates Drive lookups, template rendering, draft creation
        │   └── templates.py            # Jinja2 environment and template loader
        │
        ├── notifications/
        │   └── slack.py                # Slack webhook notifications
        │
        └── scheduler/
            └── runner.py               # Daemon loop with SIGINT/SIGTERM handling
```

---

## How it works

```
Gmail inbox
    │
    ▼
1. SEARCH  ─── from:gemini-notes@google.com subject:"21 Draw Course Production"
    │           (skips emails already labelled AutoDraft/Processed)
    │
    ▼
2. FILTER  ─── subject regex must match and capture artist name
    │           (excludes internal meetings via negative lookahead)
    │
    ▼
3. PARSE   ─── Claude API reads the email body and returns JSON:
    │           artist name, email, course topic, dates, action items
    │           Falls back to: Invited: line → Gmail inbox search
    │
    ▼
4. LOOKUP  ─── Google Drive: find _artist_edit folder + Course Outline doc
    │           Tries: pen name → legal name (from email headers) → first name only
    │
    ▼
5. RENDER  ─── Jinja2 template filled with all extracted data
    │           Markdown → HTML conversion
    │
    ▼
6. DRAFT   ─── Gmail draft created as multipart/alternative (HTML + plain text)
    │           Placed in existing thread if one is found, otherwise new email
    │
    ▼
7. LABEL   ─── Source email tagged AutoDraft/Processed
    │
    ▼
8. NOTIFY  ─── (optional) Slack message with artist name + direct link to draft
```

---

## Email layout & formatting

The email body is generated from `config/templates/artist_followup.md`. It is a Jinja2 template written in Markdown; the `markdown` library converts it to HTML before the draft is created. Gmail receives a `multipart/alternative` message containing both the HTML version and the original Markdown as plain text.

### Template source

```jinja
Hi {{ artist_first_name }},

It was great chatting with you today and discussing the vision for your course on
{{ course_subject }}. Very excited about this topic!    ...

**Course folder:** Here is where all the video, audio, and other course material
can be uploaded to:
> {{ artist_edit_link }}

**Course outline:** Where you can plan the course structure, goals, and lesson plan.
> {{ course_outline_link }}

**References from other instructors:** Helpful for inspiration in filming and planning
> {{ references_link }}

**Technical Guidelines and Deliverables**
> {{ tech_guidelines_link }}

**Deadline Dates:**
{% if outline_delivery_date %}- {{ outline_delivery_date }} - Course outline doc to be completed
{% endif %}{% if demo_video_date %}- {{ demo_video_date }} - Demo videos submitted for every shot
{% endif %}{% if artist_bio_date %}- {{ artist_bio_date }} - Send artist bio material
{% endif %}{% if contract_timeline %}- Contract timeline: {{ contract_timeline }}
{% endif %}{% if checkin_schedule %}- Check-ins: {{ checkin_schedule }}
{% endif %}{% for item in action_items %}- {{ item }}
{% endfor %}

Hope this all makes sense and is clear. ...

Marian
```

### Variable reference

| Variable | Source | Notes |
|---|---|---|
| `{{ artist_first_name }}` | Claude API — parsed from meeting notes | First name only |
| `{{ course_subject }}` | Claude API — parsed from meeting notes | Falls back to `[Course Subject]` if not found |
| `{{ artist_edit_link }}` | Google Drive lookup | Link to the artist's `_artist_edit` upload folder; shows a `NOT FOUND` placeholder if Drive search fails |
| `{{ course_outline_link }}` | Google Drive lookup | Link to the Course Outline Google Doc; `NOT FOUND` placeholder if not found |
| `{{ references_link }}` | Hard-coded in `generator.py` | Static Drive folder link shared across all artists |
| `{{ tech_guidelines_link }}` | Hard-coded in `generator.py` | Static Google Doc link shared across all artists |

### Conditional blocks (only rendered when data is present)

| Variable | Source |
|---|---|
| `{{ outline_delivery_date }}` | Claude API — extracted from notes if mentioned |
| `{{ demo_video_date }}` | Claude API — extracted from notes if mentioned |
| `{{ artist_bio_date }}` | Not currently populated by the parser — renders blank if not set |
| `{{ contract_timeline }}` | Claude API — extracted from notes if mentioned |
| `{{ checkin_schedule }}` | Claude API — extracted from notes if mentioned |
| `{{ action_items }}` | Claude API — list of specific tasks/next steps from the notes |

If none of the deadline variables are populated, the `**Deadline Dates:**` section header still appears but the list will be empty. Edit the template to remove or adjust sections that aren't relevant.

### Customising the template

1. Open `config/templates/artist_followup.md` in any text editor
2. Edit the body text freely — the Jinja2 `{{ variable }}` and `{% if %}` / `{% for %}` tags will still be evaluated
3. Add new static content anywhere; add new conditional blocks using `{% if variable %}...{% endif %}`
4. Changes take effect immediately on the next run — no restart needed

---

## Troubleshooting

**`RuntimeError: No valid credentials. Run with --setup-auth to authenticate.`**

The OAuth token has expired or is missing. Re-run:
```bash
python run.py --setup-auth
```

---

**`No new matching emails found`**

Possible causes:
- The Gemini notes email is already labelled `AutoDraft/Processed`. Remove the label in Gmail to reprocess.
- The subject line doesn't match the regex. Run with `--dry-run` and check console output. Adjust `SUBJECT_PATTERN` in `.env` if needed.
- `GEMINI_SENDER` in `.env` doesn't match the actual sender address.

---

**`[Link to _artist_edit folder - NOT FOUND]` in the draft**

The Drive lookup couldn't find the artist's folder. Check:
- `DRIVE_BASE_FOLDER` in `.env` is set to the correct shared drive path (the first `/`-separated segment must be the exact shared drive name)
- The artist folder name in Drive matches what was extracted from the meeting notes. The script tries the pen name, then the legal name found in past email threads — but if the folder uses a completely different name, it won't be found automatically.
- Your Google account has access to the shared drive.

---

**`Error loading settings: ... field required`**

`ANTHROPIC_API_KEY` is missing from `.env`. Add it:
```dotenv
ANTHROPIC_API_KEY=sk-ant-your-key-here
```
