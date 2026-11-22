# Smart Farm

A platform for managing livestock health on many farms. Any farmer can create an account for their farm, invite staff, and manage animals, health, breeding, feeding, tasks, notifications and reports. The first farm on the platform is **YPA FARM**, a goat farm in Kenya.

The stack is Django 5.2 + Django REST Framework + PostgreSQL 16 + Celery/Redis + Channels on the backend, and React 18 + Vite + TypeScript (with an installable PWA in phase 8) on the frontend.

## Build phases

| # | Phase | Status |
|---|-------|--------|
| 1 | Foundation: repository, Docker Compose, settings, CI, base models, tenancy, audit log, design tokens, app shell | **Done** |
| 2 | Accounts: sign-up, login, password reset, verification, invitations, roles, User Management, Settings | **Done** |
| 3 | Livestock: register, registration form, animal profile, weights, photos | **Done** |
| 4 | Health and calendar: health records, activities, recurrence, 4 calendar views, 2027 template, overdue job | **Done** |
| 5 | Breeding and nutrition: matings, pregnancies, births creating kids, mortality, feed stock, feeding, assessments, supplements, water & hygiene | **Done** |
| 6 | Notifications | Next |
| 7 | Dashboard and reports | |
| 8 | Mobile, offline and launch | |

## Repository layout

```
backend/
  config/            settings (base, dev, test, prod), urls, api_v1 router, asgi, wsgi, celery
  apps/
    core/            tenancy (FarmScopedModel, managers, farm resolution), permissions, errors,
                     pagination, base viewsets, health checks, Celery FarmTask
    accounts/        User, Farm, FarmMembership (+ me, me/farms)
    audit/           AuditLog, written automatically for every farm-owned change
    livestock/ health/ calendar/ breeding/ nutrition/ notifications/ reports/   (later phases)
  tests/             pytest suite; tests/testapp holds test-only models that exercise the base classes
frontend/
  src/
    api/             fetch client + types generated from the OpenAPI schema
    components/      StatusBadge, StatCard, EmptyState, LoadingState, ErrorState, Toast, layout/
    features/        one folder per module (session and placeholders for now)
    routes/          routes, navigation, role table (permissions.json)
    styles/          tokens.css (design tokens) + global.css
    i18n/            English and Kiswahili
docker-compose.yml   local stack
.env.example         every environment variable, documented
```

## Run it locally

### In the cloud with GitHub Codespaces (nothing to install)

1. Open https://github.com/2002king811/Smart-Farm and choose the branch you want to run.
2. Click **Code → Codespaces → Create codespace on <branch>**.
3. Wait for the first start (about 5–10 minutes). The stack starts by itself (`docker compose up`, without MinIO).
4. Open the **Ports** tab and click the globe icon next to **Smart Farm web app (5180)**.

Stop the codespace when you're done (**Code → Codespaces → … → Stop codespace**) so it doesn't use your free monthly hours. To restart the stack inside a codespace:

```bash
USE_S3=false docker compose up -d --build db redis mailpit migrate api websocket worker beat web
```

### With Docker (recommended)

```bash
docker compose up --build
```

| Service | URL |
|---------|-----|
| Web app (Vite dev server) | http://localhost:5180 |
| API | http://localhost:8010/api/v1/ |
| API docs (Swagger UI) | http://localhost:8010/api/docs/ |
| Health check | http://localhost:8010/api/health |
| Django admin (platform Super Admin) | http://localhost:8010/admin/ |
| Mailpit (captured email) | http://localhost:8026 |
| MinIO console | http://localhost:9011 (user `smartfarm`, password `smartfarm-dev-secret`) |

The host ports deliberately avoid the common defaults (5173, 8000, 5432, 6379, 8025, 9000), so Smart Farm can run next to other projects. If one of these ports is still taken on your machine, override it, for example:

```bash
WEB_PORT=5190 API_PORT=8020 docker compose up
```

Postgres is published on 5433 and Redis on 6380 (`DB_PORT`, `REDIS_PORT`). If you open http://localhost:5180 and see a different app, another program is using that port: pick a different `WEB_PORT`.

Compose starts `db`, `redis`, `minio` (+ `minio-setup`, which creates the bucket), `mailpit`, `migrate` (a one-off migration step), `api`, `websocket`, `worker`, `beat` and `web`. Every value in the compose file is a development default, so you don't need a `.env` file.

To create a platform super admin:

```bash
docker compose exec api python manage.py createsuperuser
```

Open http://localhost:5180 and choose **Create an account for your farm**. While developing, invitation links and SMS codes appear at http://localhost:8010/api/dev/outbox.

### On Windows without Docker (simplest)

**One click:** double-click **`windows-install.bat`**. It uses winget (built into Windows 10/11) to install Python 3.12, Node.js LTS and PostgreSQL 16, then sets up and starts Smart Farm. If it installs PostgreSQL itself, it gives it a random password and saves it only in the project's `.env` file (which git ignores).

**Or step by step:**

1. Install these three programs. Each has a normal Windows installer:
   - **Python 3.12** from https://www.python.org/downloads/ (tick "Add python.exe to PATH")
   - **Node.js LTS** from https://nodejs.org/
   - **PostgreSQL 16** from https://www.postgresql.org/download/windows/ (remember the password you choose; you don't need Stack Builder)
2. In the Smart Farm folder, double-click **`windows-setup.bat`**. Run it once; it asks for your PostgreSQL password.
3. Double-click **`windows-start.bat`**. Your browser opens **http://localhost:5180**.

This uses simple local mode (`USE_REDIS=false`): background jobs run straight away and live updates stay in memory, so neither Redis nor Docker is needed. A third window, "Smart Farm reminders", runs the scheduled jobs (reminders, overdue checks, held messages) every minute with `python manage.py run_jobs`. It's fine for one computer, but staging and production always use Redis and Celery beat.

### Without Docker

You need Python 3.12, Node 22, PostgreSQL 16 and Redis 7.

```bash
cp .env.example .env            # then set DJANGO_SECRET_KEY and DATABASE_URL
```

```bash
cd backend && python3.12 -m venv .venv && . .venv/bin/activate && pip install -r requirements/dev.txt
```

```bash
cd backend && python manage.py migrate && python manage.py runserver 8010
```

```bash
cd backend && celery -A config worker -l info
```

```bash
cd backend && uvicorn config.asgi:application --port 8011
```

```bash
cd frontend && npm install && npm run dev
```

The web app opens on http://localhost:5180 either way (with or without Docker).

## Testing and checks

Backend (from `backend/`; the tests need PostgreSQL and use `config.settings.test`):

```bash
pytest --cov
```

```bash
ruff check . && black --check . && mypy
```

Frontend (from `frontend/`):

```bash
npm test && npm run lint && npm run format:check && npm run typecheck && npm run build
```

CI (`.github/workflows/ci.yml`) runs all of these on every push and pull request. It also checks that:

- migrations are up to date (`makemigrations --check`);
- the frontend copy of the role table matches the backend (`python manage.py export_permissions --check`);
- `backend/openapi.json` and `frontend/src/api/schema.d.ts` are regenerated whenever the API changes;
- backend coverage on `apps/` is at least 85%;
- the production Docker images build.

### After changing the API or the role table

```bash
cd backend && python manage.py spectacular --file openapi.json --format openapi-json --validate
```

```bash
cd frontend && npm run api:generate
```

```bash
cd backend && python manage.py export_permissions
```

## Countries, districts and currency

- **Default country:** new farms default to **Uganda** (UGX, +256, Africa/Kampala). Sign-up asks for the country first, and then that country's districts.
- **Supported countries:** Uganda (districts), Kenya (counties), Tanzania (regions) and Rwanda (districts), served at `GET /api/v1/countries`. Any other country is accepted, with a typed area name.
- **What the country sets:** the farm's currency, time zone and phone prefix. Local numbers are stored in international format, e.g. 0772 123 456 becomes +256772123456.
- **Moving a farm to another country** (Settings → Farm profile) also switches its currency and time zone, unless they had been changed by hand.
- **Platform defaults** can be changed with `DEFAULT_COUNTRY`, `DEFAULT_CURRENCY` and `DEFAULT_PHONE_REGION`.

## Accounts and sessions (phase 2)

- **Sign-up** (`POST /api/v1/auth/signup`, 3 steps in the UI) creates the user, the farm and an Administrator membership in one transaction. It then sends an email confirmation link and an SMS code. The app can be used straight away, but SMS and WhatsApp sending stay off until the phone is confirmed.
- **Login** works with a username, email or phone number. After 5 wrong passwords the account is locked for 15 minutes, and login and code endpoints are rate-limited per IP address and per account.
- **Sessions:** the access token lasts 15 minutes and is kept in memory only. The refresh token (1 day, or 30 days with "Remember me") is an httpOnly cookie, rotated on each use, and checked against a CSRF cookie.
- **Password reset** works by email link or 6-digit SMS code. Both expire after 15 minutes, codes allow 5 tries, and only hashes are stored. A reset signs the user out everywhere.
- **Members and invitations** (Administrators only): invite by link, or create an account with a temporary password that must be changed at first login. Admins can change roles, reset passwords, and deactivate or activate members. Deactivating cuts farm access immediately and keeps all records. A farm always keeps at least one active Administrator.
- **Messages** (invitations, codes, links): email goes through Django's mail backend (Mailpit locally). SMS and WhatsApp use the console adapter until phase 6. In development, `GET /api/dev/outbox` lists recent messages so you can open links and read codes. It only exists when `DJANGO_DEBUG=true` and `MESSAGING_ADAPTER=console`.

## Livestock (phase 3)

- **Register** (`GET /api/v1/animals`):
  - Search by ID, ear tag, name or breed.
  - Filter with `sex`, `breed`, `age=kid|young|adult`, `status` (health status, comma-separated), `attention`, `location`, `group`, `breeding` and `active=true|false|all` (default: in the herd).
  - Sort with `ordering`.
- **Summary and export:** `GET /animals/summary` returns the stat-card counts. `GET /animals/export?format=csv|xlsx` exports the filtered register (managers and administrators).
- **Animal IDs:** `GET /animals/next-id` suggests the next free ID from the farm prefix (e.g. `YPA-021`). Animal IDs and ear tags are unique per farm.
- **Ages:** entering an estimated age stores an estimated birth date, so the age keeps counting. A kid is under 6 months.
- **Weights:** `GET/POST /animals/{id}/weights` lists and records weights, showing the gain since the previous one. Managers can correct or delete one at `/weights/{id}`.
- **Photos:** `GET/POST /animals/{id}/photos` (JPG, PNG or WebP, up to 10 MB). Each upload is stored at up to 1600 px with a 400 px thumbnail, and the EXIF data, including GPS location, is removed. The first photo becomes the profile photo.
- **Leaving the herd:** `POST /animals/{id}/exit` records a sale, death or cull, and `/reactivate` undoes it. The animal's history is kept.
- **Timeline:** `GET /animals/{id}/timeline` lists registration, weights, photos, status changes and moves. Later phases add health, breeding and feeding events through `TIMELINE_SOURCES`.
- **Locations and groups:** `/locations` and `/animal-groups`, managed by managers and administrators. New farms start with default pens (including Isolation Pen and Quarantine Pen) and groups.
- **Attendants** can view the register, register animals, add photos and record weights.

## Health and calendar (phase 4)

- **Health records:** `/vaccinations`, `/dewormings`, `/treatments` (with `/resolve`), `/vet-visits`, `/observations` (disease monitoring), `/inspections` and `/parasite-control`.
  - Each list can be filtered by animal or group, a date range (`date_from`, `date_to`) and status. Attendants can record and edit, but not delete.
  - `/vaccines` and `/medicines` are starter lists seeded for every farm. Managers maintain them.
- **Next dates become calendar tasks:** any record with a next or follow-up date keeps exactly one open activity on the calendar, linked to the record. Changing the date moves it, clearing the date or deleting the record removes it, and a completed task stays as history.
- **Treatments** set the animal to Under Treatment. Resolving its last open treatment returns it to Healthy, or to Pregnant if it is pregnant.
- **Withdrawal periods:** a medicine's withdrawal days fill in `withdrawal_until`, and the profile shows "Do not sell or milk until…".
- **Health alerts:** severe observations, and temperatures of 40.5 °C or more, emit a `health.alert` event. Phase 6 delivers it.
- **Activities** (`/activities`):
  - Filters: `from`, `to`, `category` (id or key), `assignee` (`me`, `none` or an id), `status` (comma-separated), `priority`, `animal`.
  - Actions: `start`, `complete`, `cancel`, `reopen` and `assign`, plus `notes` and `history` lists.
  - Attendants see and work only their own tasks; `/activities/calendar` shows them the whole farm, read-only.
- **Repeating activities:** a `repeat` preset (weekly, monthly, quarterly, yearly) or a `recurrence_rule` (RRULE) creates occurrences 12 months ahead, and a daily job keeps the series extended.
  - Edits apply with `scope=this` or `scope=following`. Changing how a series repeats from one occurrence ends the old series the day before.
- **Calendar views:** `/activities/calendar?view=month|week|day|agenda&date=YYYY-MM-DD` (weeks start on Monday).
- **Overdue job:** the Celery task `calendar.mark_overdue` runs hourly at :05, so each farm switches past-due tasks to Overdue just after its own midnight. You can also run it by hand: `python manage.py mark_overdue [--farm slug] [--as-of YYYY-MM-DD]`.
- **2027 health calendar:** `/activity-templates` lists the template, and `POST /activity-templates/health-calendar-2027/apply` adds the 23 planned activities. Applying it again skips what is already there.
- **Activity categories:** Vaccination, Deworming, Parasite Control, Treatment, Vet Visit, Health Inspection, Breeding, and Feeding & Nutrition.

## Breeding and nutrition (phase 5)

- **Matings** (`/matings`, with `/scan` and `/abort`):
  - The expected kidding date is the mating date + 150 days, and you can change it. Saving a mating adds a pregnancy-scan task 35 days later and an "Expected kidding" task, both on the calendar.
  - A doe can have only one open mating at a time.
  - A confirmed scan sets the doe to Pregnant. "Not pregnant" or an abortion returns her to Open.
- **Pregnancies:** `/pregnancies` derives each pregnancy's progress, days pregnant, days remaining and trimester from the open matings.
- **Births:** `POST /births` with a list of `kids` (sex, name, ear tag, birth weight, alive).
  - Each live kid becomes an Animal with the next ID, its dam, sire, location and a first weight record. Stillborn kids are only counted.
  - The birth closes the doe's open mating as Kidded, sets her to Lactating and completes the kidding task.
  - Births can be corrected but not deleted, because the kids have their own records.
- **Kids:** `/kids` lists animals under 6 months with their birth weight, latest weight and average daily gain. `/kids/{id}/growth` gives the full weight series.
- **Deaths:** `/mortality` records a death. The animal leaves the herd (exit reason: died), any open mating is closed, and an urgent `health.alert` event is emitted. Deleting a death recorded by mistake brings the animal back.
- **Feed items:** `/feed-items` (starter items are seeded per farm), plus `POST /feed-items/{id}/stock` for stock in (purchase), a stock count (adjustment) or waste.
  - Stock is always the sum of the item's movements. `/feed-stock` lists every movement.
  - Days left = stock ÷ average daily use over the last 14 days.
  - Crossing the reorder level emits `feed.low_stock` once.
- **Feeding:** `/feeding-records` takes the quantity out of stock and refuses more than is in store. Editing or deleting a record puts the stock right. Attendants can record feeding.
- **Other nutrition records:** `/nutrition-assessments` (a next date adds a calendar task), `/supplementation` (can take from stock), `/water-hygiene` (scored out of 5), and `/nutrition/summary`.
- **Sessions:** a refresh token replaced by rotation stays usable for 60 seconds, so a page reload or a second tab doesn't log people out. Logout, password changes and deactivation still end sessions at once.

## Notifications (phase 6)

Code emits one event (`apps/notifications/events.emit`); `apps/notifications/services.py` turns it into:

- one **in-app notification** per recipient (the bell badge, the Notifications page), and
- one **message per external channel** the person has switched on (WhatsApp, SMS, email), sent by a background task and tracked as Queued → Sent → Delivered → Read, or Failed with the reason.

**Who gets what.** Defaults per event and channel follow the build spec (`catalog.py`); each person changes them in **Settings → Notifications**. The channels picked at sign-up are the starting point.

| Event | Goes to |
|---|---|
| Upcoming / due today / vaccination / deworming reminders | the assignee, or managers if nobody is assigned |
| Overdue | the assignee and managers |
| Task assigned, activity completed | the person concerned |
| Health alert (severe observation, fever, death), low feed stock | administrators and farm managers |
| Message allowance warning | administrators |

**Rules.**
- SMS and WhatsApp need a confirmed mobile number; email needs a confirmed address. WhatsApp also needs the person's consent ("Yes, send me WhatsApp messages"). A changed number needs consent again.
- **Quiet hours** (default 21:00–06:00, farm time zone) hold SMS and WhatsApp until they end. Urgent health alerts still go straight out.
- Failed sends are retried 3 times (after 1, 2 and 4 minutes). Errors that won't fix themselves (wrong number, template not approved, missing keys) fail at once.
- Each farm has a monthly allowance (SMS 500, WhatsApp 1,000). Administrators get a warning at 80 %, and non-urgent messages stop at 100 %. Usage is shown to administrators under Settings → Notifications.

**Schedules** (farm local time; `notifications.run_schedules` every 15 minutes, `notifications.release_due` every minute):
- 06:00: reminders N days before an activity (its "remind me" days) and "due today";
- 07:00: overdue activities (once per activity and due date);
- each person's digest time (default 07:00): the daily summary, by email by default.

**Providers.** Everything uses the **console** adapter except staging and production: messages are logged and shown at http://localhost:8010/api/dev/outbox. Set `MESSAGING_ADAPTER=live` (or `SMS_ADAPTER=africastalking`, `WHATSAPP_ADAPTER=whatsapp_cloud`) and the keys in `.env` to send for real:
- **Africa's Talking** (SMS): `AFRICASTALKING_USERNAME` (`sandbox` uses the sandbox), `AFRICASTALKING_API_KEY`, `AFRICASTALKING_SENDER_ID`.
- **WhatsApp Cloud API**: `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN`. Templates must be approved in Meta Business Manager in English (`en`) and Kiswahili (`sw`), named as in `catalog.WHATSAPP_TEMPLATES` (e.g. `smartfarm_task_assigned`), with body `{{1}}` title and `{{2}}` details. Activity templates add two quick-reply buttons: "Mark done" and "Reschedule".
- **Email**: Django's mail settings (`EMAIL_*`), HTML and plain text.

**Webhooks** (set these URLs in each provider's dashboard):
- WhatsApp: `/api/v1/webhooks/whatsapp` (verified with the verify token; posts must carry a valid signature). It records delivery and read receipts, and the buttons or a reply of `1` (mark done) / `2` (move to tomorrow).
- Africa's Talking: `/api/v1/webhooks/sms/delivery?token=…` (delivery reports) and `/api/v1/webhooks/sms/inbound?token=…` (replies: `1`, `2`, `STOP`).
- Email: `/api/v1/webhooks/email?token=…` (SendGrid-style events; bounces and complaints stop email to that address).

**Live updates.** The browser opens `/ws/notifications?token=<access token>`, so the bell updates at once. If the connection fails, it checks every 60 seconds instead.

**API.** `/notifications` (`?unread=true`, `?urgent=true`), `/notifications/{id}/read`, `/notifications/read-all`, `/notifications/unread-count`, `/notifications/test`, `/notifications/usage` (administrators), `/notification-preferences` (GET/PUT the matrix and quiet hours), `/channel-contacts` and `PATCH /channel-contacts/{email|sms|whatsapp}` (opt in or out).

## End-to-end tests

Start the API with a throwaway database, then run Playwright:

```bash
cd backend && DATABASE_URL=postgres://postgres:postgres@localhost:5432/smartfarm_e2e USE_REDIS=false DJANGO_DEBUG=true python manage.py migrate && DATABASE_URL=postgres://postgres:postgres@localhost:5432/smartfarm_e2e USE_REDIS=false DJANGO_DEBUG=true python manage.py runserver 8010
```

```bash
cd frontend && DATABASE_URL=postgres://postgres:postgres@localhost:5432/smartfarm_e2e npm run e2e
```

The health-calendar journey runs `manage.py mark_overdue` against the same database, so give the test run the same `DATABASE_URL` as the API.


## How multi-farm tenancy works

Every record belongs to exactly one farm, and the backend enforces this at the model layer, not only in views.

1. **Base class.** Every farm-owned model extends `apps.core.models.FarmScopedModel`. It provides a UUID `id`, `farm`, `created_at`, `updated_at`, `created_by`, `updated_by` and `deleted_at` (soft delete).
2. **Active farm.** Each API request names its farm in the `X-Farm-ID` header (or the JWT `farm_id` claim). `FarmContextMixin` checks it against the user's **active** membership before any permission check. If the user is not a member, the farm is unknown or the membership is inactive, the response is **404, never 403**, so farm IDs cannot be probed. Members of a suspended farm get 403 with a reason.
3. **Automatic scoping.** The active farm goes into a request context (`contextvars`). The default manager `Model.objects` then adds `farm_id = <active farm>` to every query and hides soft-deleted rows. Base viewsets also filter explicitly, as a second layer.
4. **Write guards.** Saving refuses to write a row for another farm or to move a row between farms. Every foreign key or many-to-many link to another farm-owned row must stay inside the same farm. Serializer foreign keys only accept IDs from the active farm.
5. **Background work.** Celery tasks that touch farm data use `FarmTask` and are called with `farm_id=…`. Management commands use `with farm_context(farm_id):`.
6. **Escape hatch.** `Model.unscoped` returns every row of every farm. It is for platform code only, never request handlers.

`tests/test_tenancy_isolation.py` discovers every farm-scoped endpoint from the URL configuration. For each one it creates records in two farms and proves that list, detail, update and delete never touch the other farm's data. The test fails when:

- a new farm-owned model has no factory in `tests/factories.py`;
- a new `/api/v1/` endpoint is not farm-scoped and is not explicitly allow-listed.

So every module added in later phases is covered automatically.

## Roles and permissions

The role table from the spec (section 3) lives in one file: `backend/apps/core/permissions_matrix.json`.

- **Backend.** Each view declares `permission_module` (and optionally `action_permissions`). `FarmModulePermission` then checks the user's role **on the active farm**.
- **Frontend.** The frontend reads a checked copy (`frontend/src/routes/permissions.json`) and hides anything a role cannot use.
- **API.** `GET /api/v1/me/farms` also returns the rules for each membership.

## Audit log

Every create, update, soft delete, restore and status change on a farm-owned model is recorded automatically. Each entry holds the user, IP, request ID, changed fields and before/after values. Entries are append-only. Administrators can read them at `GET /api/v1/audit-logs`.

## API conventions

- Versioned under `/api/v1/`, with no trailing slashes. OpenAPI docs are at `/api/docs/`.
- All errors use one shape: `{"errors": {"field": ["message"]}}`. Errors that aren't about a field use `"detail"`.
- Lists use cursor pagination with a total count: `{"count", "next", "previous", "results"}`. They accept `?page_size=` (max 200), `?search=`, `?ordering=` and per-endpoint filters.
- `GET /api/health` (database and Redis) and `GET /api/health/live` are for load balancers and uptime checks.
- Logs are structured JSON and carry `request_id`, `farm_id` and `user_id`. Responses echo `X-Request-ID`.

## Design system

- **Tokens.** Colours, type, spacing, radii and shadows live in `frontend/src/styles/tokens.css`. The brand palette is `#1B5E20`, `#2E7D32`, `#E8F5E9` and `#66BB6A`, with Manrope for headings and Inter for body text. Fonts are self-hosted so they work offline.
- **Status colours.** Every status maps to a colour in exactly one place: `StatusBadge` (`frontend/src/components/StatusBadge.tsx`).
- **Layouts.** Administrators and managers get the desktop shell (sidebar, header and farm switcher). Livestock attendants get the phone layout with bottom navigation (Home, Tasks, Animals, Calendar, Alerts).

## Deployment (outline; completed in phase 8)

- **One backend image, four roles** (`backend/Dockerfile`, target `prod`):
  - `api`: `gunicorn config.wsgi`
  - `websocket`: `uvicorn config.asgi:application`
  - `worker`: `celery -A config worker`
  - `beat`: `celery -A config beat`
- **Web image** (`frontend/Dockerfile`, target `prod`): nginx serving the built SPA, with security headers and a Content Security Policy.
- **Migrations** run as a separate release step: `python manage.py migrate --noinput`.
- **Production settings** are `config.settings.prod`: HTTPS redirect, HSTS, secure cookies and Argon2 password hashing. `MESSAGING_ADAPTER` must be set explicitly.
- **Secrets** are environment variables only (see `.env.example`), never in the repository or the database.
