import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_application_1/validators.dart';

void main() {
  test('accepts normal email addresses', () {
    for (final ok in [
      'name@example.com',
      'first.last@mail.example.sa',
      'user+tag@gmail.com',
      'a_b-c@my-domain.org',
      '  padded@example.com  ',
    ]) {
      expect(Validators.isValidEmail(ok), isTrue, reason: ok);
    }
  });

  test('rejects malformed email addresses', () {
    for (final bad in [
      'plainaddress',
      'name@',
      '@example.com',
      'name@example',
      'name@example.c',
      'name@example.123',
      'a..b@example.com',
      '.name@example.com',
      'name.@example.com',
      'name@-example.com',
      'name@example-.com',
      'name@exa_mple.com',
      'name@example..com',
      'na me@example.com',
      'name@@example.com',
    ]) {
      expect(Validators.isValidEmail(bad), isFalse, reason: bad);
    }
  });

  test('validator messages', () {
    expect(Validators.email(''), 'Email is required');
    expect(Validators.email('x@y'), contains('valid email'));
    expect(Validators.email('x@example.com'), isNull);
  });
}
