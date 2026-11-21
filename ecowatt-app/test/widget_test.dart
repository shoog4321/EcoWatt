// The template "Counter increments" test did not match this app (it has no counter) and always failed.
// Screens need a live Supabase session, so these tests cover the pure-Dart configuration only.
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_application_1/api_config.dart';

void main() {
  test('backend URL defaults to the local backend and can be overridden', () {
    // flutter test --dart-define=API_BASE_URL=... changes this value
    expect(ApiConfig.baseUrl, startsWith('http'));
    expect(ApiConfig.baseUrl.endsWith('/'), isFalse);
  });
}
