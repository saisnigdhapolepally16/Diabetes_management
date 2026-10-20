# Diabetrix Backend — API Reference

## Stack
- **Python Flask** — lightweight web framework
- **SQLite** — single-file relational database (`diabetrix.db`)
- **No external services required** — runs entirely offline

---

## How to Run

```bash
# 1. Install dependencies (one time only)
pip install -r requirements.txt

# 2. Start the server
python app.py

# Server starts at: http://127.0.0.1:5000
# Database file:    diabetrix.db  (auto-created on first run)
```

---

## Database Schema

```
users
  id, name, email, password (hashed), created_at

profiles
  user_id (FK), age, gender, weight_kg, height_cm,
  lifestyle, dtype, diagnosed_year, target_low, target_high,
  doctor_name, allergies, meds_text, step_goal, steps_today

glucose_readings
  id, user_id (FK), value, meal_context, note,
  classification, recorded_at

medications
  id, user_id (FK), name, dose, time_of_day,
  frequency, is_done, created_at

emergency_contacts
  id, user_id (FK), name, phone, relationship, created_at

safety_log
  id, user_id (FK), log_type, message, logged_at

sessions
  token, user_id (FK), created_at
```

---

## Authentication

All protected routes require:
```
Authorization: Bearer <token>
```
Token is returned from `/api/auth/login` or `/api/auth/signup`.

---

## API Endpoints

### Auth
| Method | Route                  | Body                                  | Description        |
|--------|------------------------|---------------------------------------|--------------------|
| POST   | /api/auth/signup       | `{name, email, password}`             | Register user      |
| POST   | /api/auth/login        | `{email, password}`                   | Login, get token   |
| POST   | /api/auth/logout       | —                                     | Invalidate token   |

### Profile
| Method | Route              | Body / Params                         | Description        |
|--------|--------------------|---------------------------------------|--------------------|
| GET    | /api/profile       | —                                     | Get user profile   |
| PUT    | /api/profile       | `{age, gender, weight_kg, ...}`       | Update profile     |
| PATCH  | /api/profile/steps | `{steps}`                             | Update step count  |

### Glucose
| Method | Route              | Body / Params                         | Description        |
|--------|--------------------|---------------------------------------|--------------------|
| GET    | /api/glucose       | `?days=30`                            | Get readings       |
| POST   | /api/glucose       | `{value, meal_context, note}`         | Add reading        |
| DELETE | /api/glucose/{id}  | —                                     | Delete reading     |

### Analytics & AI
| Method | Route              | Params   | Description                        |
|--------|--------------------|----------|------------------------------------|
| GET    | /api/analytics     | `?days=` | Stats: avg, max, min, in-range %   |
| GET    | /api/ai/predict    | —        | Risk level + health score + advice |

### Medications
| Method | Route                        | Body                          | Description      |
|--------|------------------------------|-------------------------------|------------------|
| GET    | /api/medications             | —                             | List all meds    |
| POST   | /api/medications             | `{name, dose, time, freq}`    | Add medication   |
| PATCH  | /api/medications/{id}/toggle | —                             | Mark done/undone |
| DELETE | /api/medications/{id}        | —                             | Delete med       |

### Emergency Contacts
| Method | Route              | Body                          | Description        |
|--------|--------------------|-------------------------------|--------------------|
| GET    | /api/contacts      | —                             | List contacts      |
| POST   | /api/contacts      | `{name, phone, relationship}` | Add contact        |
| DELETE | /api/contacts/{id} | —                             | Delete contact     |

### Safety
| Method | Route                  | Body                              | Description         |
|--------|------------------------|-----------------------------------|---------------------|
| GET    | /api/safety/log        | —                                 | Get safety history  |
| POST   | /api/safety/log        | `{type, message}`                 | Add safety event    |
| POST   | /api/safety/checkin    | —                                 | Confirm user is OK  |
| POST   | /api/emergency/alert   | `{location, reason, symptoms[]}`  | Trigger alert       |

### Reports
| Method | Route       | Params   | Description            |
|--------|-------------|----------|------------------------|
| GET    | /api/report | `?days=` | Generate health report |

### Utility
| Method | Route             | Description                     |
|--------|-------------------|---------------------------------|
| GET    | /api/health       | Server + database health check  |
| GET    | /api/admin/users  | List all users (dev only)       |

---

## Example: Login + Log Glucose

```python
import requests

BASE = "http://127.0.0.1:5000"

# Login
res   = requests.post(f"{BASE}/api/auth/login",
          json={"email": "user@test.com", "password": "pass123"})
token = res.json()["token"]
headers = {"Authorization": f"Bearer {token}"}

# Log glucose reading
requests.post(f"{BASE}/api/glucose",
  headers=headers,
  json={"value": 145, "meal_context": "after_meal", "note": "had rice"})

# Get AI prediction
ai = requests.get(f"{BASE}/api/ai/predict", headers=headers).json()
print(ai["message"])
```

---

## Connecting the Frontend

In your `app.js`, the frontend currently uses `localStorage` only.
To connect it to this backend, set `API_BASE` at the top of `app.js`:

```js
const API_BASE = 'http://127.0.0.1:5000/api';
```

Then replace `saveApp()` / `loadApp()` calls with `fetch()` calls to the API.
The token should be stored in `localStorage` after login and sent as
`Authorization: Bearer <token>` on every request.

---

## Backup

Your entire database is one file: `diabetrix.db`

To back it up:
```bash
cp diabetrix.db diabetrix_backup_2024.db
```

That's it. No export commands, no dump scripts.