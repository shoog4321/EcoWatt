import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

import 'api_config.dart';
import 'user_storage.dart';

/// Error from the EcoWatt backend with a user-readable [message] and a
/// machine-readable [code] (e.g. `bill_invalid`, `bill_inconsistent`).
class AdviceApiException implements Exception {
  final String code;
  final String message;
  const AdviceApiException(this.code, this.message);

  @override
  String toString() => message;
}

/// Talks to the backend for bill analysis and advice generation.
/// Advice itself is still READ from Supabase (existing RLS policies).
class AdviceApi {
  static SupabaseClient get _client => Supabase.instance.client;

  /// Headers carrying the signed-in user's Supabase session.
  static Map<String, String> authHeaders() {
    final token = _client.auth.currentSession?.accessToken;
    return {if (token != null) 'Authorization': 'Bearer $token'};
  }

  /// Validates the bill on the server, runs the rule engine, and queues
  /// advice generation. Throws [AdviceApiException] when the bill is rejected.
  /// Returns the backend's advice_status: "pending" (new advice is being
  /// generated) or "kept" (an edited bill whose advice the user already applied).
  static Future<String?> analyzeBill(String billId) async =>
      (await _post('/bills/$billId/analyze'))['advice_status']?.toString();

  /// Re-runs advice generation for a bill (e.g. after a failed attempt).
  static Future<void> regenerate(String billId) async {
    await _post('/bills/$billId/advice/regenerate');
  }

  static Future<Map<String, dynamic>> _post(String path) async {
    final res = await http
        .post(Uri.parse('${ApiConfig.baseUrl}$path'), headers: authHeaders())
        .timeout(const Duration(seconds: 30));

    if (res.statusCode >= 200 && res.statusCode < 300) {
      try {
        final body = jsonDecode(res.body);
        return body is Map
            ? Map<String, dynamic>.from(body)
            : <String, dynamic>{};
      } catch (_) {
        return <String, dynamic>{};
      }
    }

    var code = 'error';
    var message = 'Could not request advice (HTTP ${res.statusCode}).';
    try {
      final body = jsonDecode(res.body);
      final detail = body is Map ? body['detail'] : null;
      if (detail is Map) {
        code = detail['code']?.toString() ?? code;
        message = detail['message']?.toString() ?? message;
      } else if (detail is String) {
        message = detail;
      }
    } catch (_) {
      // keep the generic message
    }
    throw AdviceApiException(code, message);
  }

  /// Reads an AC energy-label photo on the backend and returns the fields
  /// (grade, capacity, efficiency, yearly kWh). Nothing is stored.
  /// Throws [AdviceApiException] with a readable message on failure.
  static Future<Map<String, dynamic>> scanAcLabel(
    List<int> bytes,
    String filename,
  ) async {
    final request =
        http.MultipartRequest(
            'POST',
            Uri.parse('${ApiConfig.baseUrl}/analyze-ac-label'),
          )
          ..headers.addAll(authHeaders())
          ..files.add(
            http.MultipartFile.fromBytes('file', bytes, filename: filename),
          );
    final res = await http.Response.fromStream(
      await request.send().timeout(const Duration(seconds: 180)),
    );
    Map<String, dynamic> body = {};
    try {
      // The server sends JSON without a charset: decode as UTF-8 so Arabic (e.g. the grade letter) is kept.
      final decoded = jsonDecode(utf8.decode(res.bodyBytes));
      if (decoded is Map) body = Map<String, dynamic>.from(decoded);
    } catch (_) {}
    if (res.statusCode == 200) return body;
    final detail = body['detail'];
    throw AdviceApiException(
      'label_scan_failed',
      detail is String
          ? detail
          : 'Could not read the label (HTTP ${res.statusCode}).',
    );
  }

  /// Latest advice-generation job for the selected home, or null.
  /// Shape: {bill_id, status: pending|running|done|failed, error, updated_at}.
  /// Reads the `advice_jobs` table (clients can read their own rows only).
  static Future<Map<String, dynamic>?> latestJob() async {
    final home = await UserStorage.getSelectedHome();
    if (home == null) return null;

    final ids = ((home['bills'] as List?) ?? [])
        .map((b) => (b as Map)['id'].toString())
        .toList();
    if (ids.isEmpty) return null;

    final rows = await _client
        .from('advice_jobs')
        .select('bill_id,status,error,updated_at')
        .inFilter('bill_id', ids)
        .order('updated_at', ascending: false)
        .limit(1);

    return rows.isEmpty ? null : Map<String, dynamic>.from(rows.first);
  }
}
