# Content AI Web

Flutter Web frontend for the existing FastAPI backend. Native Android, iOS,
desktop, and mobile-app targets are outside the project scope.

## Screens

- Login
- Register
- Dashboard
- Upload and analyze clip
- My analysis history

## Backend base URL

Default base URL in code:

`http://127.0.0.1:8000`

## Run

```powershell
cd frontend_flutter
flutter pub get
flutter run -d edge --dart-define=API_BASE_URL=http://127.0.0.1:8000
```
