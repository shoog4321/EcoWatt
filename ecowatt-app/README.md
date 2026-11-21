# EcoWatt
**Intelligent Assistance for Sustainable Household Electricity Consumption**

## Overview
EcoWatt is a smart mobile application developed as a graduation project to help households across **Saudi Arabia** optimize their electricity usage. By analyzing monthly electricity bills and comparing them against regional behavioral baselines, the app empowers users to make sustainable energy choices. 

## UI/UX Design & Prototype
You can explore the user interface and user experience flow of EcoWatt through our interactive Figma prototype:
**[Link to Figma Prototype](https://www.figma.com/make/2IxOfrimLOj24uJjhifI50/EcowattPrototype?p=f&t=f4y9TmiYyc4G4AdN-0&fullscreen=1)**

## Geographic Scope
The data modeling and features of EcoWatt are designed to serve households across the **Kingdom of Saudi Arabia**, utilizing national statistics to provide accurate regional insights.

## Running the app
The app needs the EcoWatt backend (separate `ecowatt-backend` project: FastAPI, rule engine, advice jobs, bill OCR) and,
for personalized advice, its GPU service. See the backend README for setup.

```bash
flutter pub get
flutter run -d chrome --web-port 5050 --dart-define=API_BASE_URL=http://127.0.0.1:8080
```
- iOS Simulator: `open -a Simulator`, then the same command with `-d iPhone`.
- Physical phone: set `API_BASE_URL` to the computer's LAN IP or a deployed backend (`127.0.0.1` is the phone itself).
- `lib/api_config.dart` holds the backend URL and `lib/advice_api.dart` the backend calls. `lib/supabase_config.dart`
  holds the project URL and the public anon key (never the service/secret key).

After a bill is confirmed, the app calls `POST /bills/{id}/analyze`. The advice screen shows "Preparing your advice..."
until the backend has generated advice (about a minute while the GPU is on), then lists it.

Home also has **Check your AC's energy label**: a bottom sheet that scans a SASO energy label (`POST /analyze-ac-label`)
and shows the grade, what it means, capacity, yearly kWh and a tip. Nothing is stored.

Tests: `flutter test` (13 tests) · Lint: `flutter analyze` (no issues).
