import 'package:supabase_flutter/supabase_flutter.dart';

/// A short, readable message for a failed login instead of the raw
/// Supabase exception (e.g. "AuthApiException(message: Invalid login
/// credentials, statusCode: 400, code: invalid_credentials)").
String loginErrorMessage(Object error) {
  if (error is AuthRetryableFetchException) return _offline;
  if (error is AuthException) {
    final code = error.code ?? '';
    if (code == 'invalid_credentials' ||
        error.message.toLowerCase().contains('invalid login')) {
      return 'Incorrect email or password. Please try again.';
    }
    if (code == 'email_not_confirmed') {
      return 'Please confirm your email first. Check your inbox for the link.';
    }
    if (code.contains('rate_limit') || error.statusCode == '429') {
      return 'Too many attempts. Please wait a minute and try again.';
    }
    if (code == 'user_banned') {
      return 'This account has been disabled.';
    }
  }
  final text = error.toString();
  if (text.contains('SocketException') ||
      text.contains('ClientException') ||
      text.contains('Failed host lookup')) {
    return _offline;
  }
  return "We couldn't log you in. Please try again.";
}

const _offline =
    "Can't connect right now. Check your internet connection and try again.";
