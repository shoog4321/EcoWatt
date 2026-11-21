/// Where the EcoWatt backend (FastAPI) lives.
///
/// Override at build/run time instead of editing code:
///   flutter run --dart-define=API_BASE_URL=https://your-backend.example.com
///
/// Defaults to the local machine. On the Android emulator use
/// http://10.0.2.2:8080 ; on a physical phone use the computer's LAN IP or
/// the deployed URL (127.0.0.1 would point at the phone itself).
class ApiConfig {
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8080',
  );
}
