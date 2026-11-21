import 'package:flutter_test/flutter_test.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'package:flutter_application_1/auth_messages.dart';

void main() {
  test('login errors are shown in plain words, never as raw exceptions', () {
    expect(
      loginErrorMessage(
        const AuthApiException(
          'Invalid login credentials',
          statusCode: '400',
          code: 'invalid_credentials',
        ),
      ),
      'Incorrect email or password. Please try again.',
    );
    expect(
      loginErrorMessage(
        const AuthApiException(
          'Email not confirmed',
          statusCode: '400',
          code: 'email_not_confirmed',
        ),
      ),
      contains('confirm your email'),
    );
    expect(
      loginErrorMessage(
        const AuthApiException(
          'Too many requests',
          statusCode: '429',
          code: 'over_request_rate_limit',
        ),
      ),
      contains('Too many attempts'),
    );
    expect(
      loginErrorMessage(AuthRetryableFetchException(message: 'x')),
      contains("Can't connect"),
    );
    expect(
      loginErrorMessage(Exception('SocketException: Connection refused')),
      contains("Can't connect"),
    );
    final other = loginErrorMessage(Exception('boom'));
    expect(other, "We couldn't log you in. Please try again.");
    for (final m in [other]) {
      expect(m, isNot(contains('Exception')));
    }
  });
}
