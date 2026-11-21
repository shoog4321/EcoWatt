/// Shared form validators.
class Validators {
  // local part: letters, digits and . _ % + - ; no leading, trailing or double dots
  // domain: labels of letters/digits/hyphens (not starting or ending with a hyphen), a letters-only TLD of 2+
  static final RegExp _email = RegExp(
    r'^[A-Za-z0-9_%+-]+(\.[A-Za-z0-9_%+-]+)*'
    r'@([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$',
  );

  static bool isValidEmail(String value) {
    final email = value.trim();
    return email.length <= 254 && _email.hasMatch(email);
  }

  /// For TextFormField.validator.
  static String? email(String? value) {
    if (value == null || value.trim().isEmpty) return 'Email is required';
    if (!isValidEmail(value)) {
      return 'Enter a valid email, e.g. name@example.com';
    }
    return null;
  }
}
