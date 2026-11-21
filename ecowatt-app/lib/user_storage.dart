import 'package:shared_preferences/shared_preferences.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

class UserStorage {
  static const String currentUserKey = 'current_user_email';

  static SupabaseClient get _client => Supabase.instance.client;

  // ─────────────────────────────────────────────────────────────
  // Session helpers
  // ─────────────────────────────────────────────────────────────

  static Future<void> saveCurrentUser(String email) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(currentUserKey, email);
  }

  static Future<String?> getCurrentUserEmail() async {
    final authUser = _client.auth.currentUser;
    if (authUser?.email != null) return authUser!.email;
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(currentUserKey);
  }

  // ─────────────────────────────────────────────────────────────
  // SIGNUP — creates auth user + profile + first home
  // ─────────────────────────────────────────────────────────────
  static Future<void> saveUser({
    required String email,
    required Map<String, dynamic> data,
  }) async {
    final password = data['password'] as String;

    // 1. Create Supabase Auth user
    final authRes = await _client.auth.signUp(email: email, password: password);

    final userId = authRes.user?.id;
    if (userId == null) {
      throw Exception('Signup failed: no user returned');
    }

    // 2. Insert User profile row
    await _client.from('User').insert({
      'id': userId,
      'firstName': data['firstName'] ?? '',
      'lastName': data['lastName'] ?? '',
      'email': email,
      'phoneNum': data['phone'],
      'selected_home_id': null,
    });

    // 3. Insert first Household
    final homes = (data['homes'] as List).cast<Map>();
    if (homes.isNotEmpty) {
      final firstHome = Map<String, dynamic>.from(homes.first);
      final householdId = await _insertHousehold(userId, firstHome);

      // 4. Point user at their new home
      await _client
          .from('User')
          .update({'selected_home_id': householdId})
          .eq('id', userId);
    }

    await saveCurrentUser(email);
  }
  // ─────────────────────────────────────────────────────────────
  // GET user
  // ─────────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>?> getUser(String email) async {
    final userId = _client.auth.currentUser?.id;
    if (userId == null) return null;

    final row = await _client
        .from('User')
        .select()
        .eq('id', userId)
        .maybeSingle();

    if (row == null) return null;

    final homes = await getHomes();

    return {
      'firstName': row['firstName'],
      'lastName': row['lastName'],
      'email': row['email'],
      'phone': row['phoneNum'],
      'selectedHomeId': row['selected_home_id'],
      'homes': homes,
    };
  }

  static Future<Map<String, dynamic>?> getCurrentUser() async {
    final email = await getCurrentUserEmail();
    if (email == null) return null;
    return getUser(email);
  }

  // ─────────────────────────────────────────────────────────────
  // HOMES
  // ─────────────────────────────────────────────────────────────

  static Future<List<Map<String, dynamic>>> getHomes() async {
    final userId = _client.auth.currentUser?.id;
    if (userId == null) return [];

    final rows = await _client
        .from('Household')
        .select()
        .eq('user_id', userId)
        .order('lastUpdated', ascending: true);

    final homes = <Map<String, dynamic>>[];
    for (final row in rows) {
      homes.add(await _householdToDart(row));
    }
    return homes;
  }

  static Future<Map<String, dynamic>?> getSelectedHome() async {
    final userId = _client.auth.currentUser?.id;
    if (userId == null) return null;

    final userRow = await _client
        .from('User')
        .select('selected_home_id')
        .eq('id', userId)
        .maybeSingle();

    final selectedId = userRow?['selected_home_id'];
    final homes = await getHomes();

    if (homes.isEmpty) return null;

    if (selectedId != null) {
      for (final h in homes) {
        if (h['id'] == selectedId) return h;
      }
    }
    return homes.first;
  }

  static Future<void> selectHome(String homeId) async {
    final userId = _client.auth.currentUser?.id;
    if (userId == null) return;

    await _client
        .from('User')
        .update({'selected_home_id': homeId})
        .eq('id', userId);
  }

  static Future<void> addHome(Map<String, dynamic> home) async {
    final userId = _client.auth.currentUser?.id;
    if (userId == null) return;

    final newId = await _insertHousehold(userId, home);

    await _client
        .from('User')
        .update({'selected_home_id': newId})
        .eq('id', userId);
  }

  /// Saves the home and syncs its bills. Returns the ids of bills that were
  /// newly inserted, so callers can ask the backend to analyse them.
  static Future<List<String>> updateHome(
    Map<String, dynamic> updatedHome,
  ) async {
    final id = updatedHome['id'] as String;

    await _client
        .from('Household')
        .update({
          'homeName': updatedHome['homeName'],
          'region': updatedHome['region'],
          'housingType': _normalizeHousingType(updatedHome['housingType']),
          'numberOfResidents':
              int.tryParse(updatedHome['residents']?.toString() ?? '1') ?? 1,
          'cookingFuel': _normalizeCookingFuel(updatedHome['cookingFuel']),
          'acType': _normalizeAcType(updatedHome['acType']),
          'hasInsulation': updatedHome['insulation'] == 'Yes',
          'homeSize': updatedHome['homeSize'],
          'behaviorAnswers': updatedHome['behaviorAnswers'] ?? {},
          'behaviorCompleted': updatedHome['behaviorCompleted'] ?? false,
          'appliedAdvice': updatedHome['appliedAdvice'] ?? [],
          'lastUpdated': DateTime.now().toUtc().toIso8601String(),
        })
        .eq('household_id', id);

    return _syncBills(id, updatedHome['bills'] ?? []);
  }

  static Future<void> logout() async {
    await _client.auth.signOut();
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(currentUserKey);
  }

  // ─────────────────────────────────────────────────────────────
  // PRIVATE HELPERS
  // ─────────────────────────────────────────────────────────────

  static Future<String> _insertHousehold(
    String userId,
    Map<String, dynamic> home,
  ) async {
    final row = await _client
        .from('Household')
        .insert({
          'user_id': userId,
          'homeName': home['homeName'] ?? '',
          'region': home['region'] ?? '',
          'housingType': _normalizeHousingType(home['housingType']),
          'numberOfResidents':
              int.tryParse(home['residents']?.toString() ?? '1') ?? 1,
          'cookingFuel': _normalizeCookingFuel(home['cookingFuel']),
          'acType': _normalizeAcType(home['acType']),
          'hasInsulation': home['insulation'] == 'Yes',
          'homeSize': home['homeSize'],
          'behaviorAnswers': home['behaviorAnswers'] ?? {},
          'behaviorCompleted': home['behaviorCompleted'] ?? false,
          'appliedAdvice': home['appliedAdvice'] ?? [],
        })
        .select('household_id')
        .single();

    return row['household_id'] as String;
  }

  // ─────────────────────────────────────────────────────────────
  // Enum normalizers — Dart display strings → Postgres enum values
  // ─────────────────────────────────────────────────────────────

  static String _normalizeHousingType(dynamic raw) {
    final s = (raw ?? '').toString().toLowerCase();
    if (s.contains('villa') && s.contains('floor')) return 'Floor in Villa';
    if (s.contains('villa')) return 'Villa';
    if (s.contains('traditional') && s.contains('floor')) {
      return 'Floor in Traditional';
    }
    if (s.contains('traditional')) return 'Traditional House';
    if (s.contains('apartment')) return 'Apartment';
    if (s.contains('other')) return 'Other';
    return 'Apartment';
  }

  static String _normalizeCookingFuel(dynamic raw) {
    final s = (raw ?? '').toString().toLowerCase();
    if (s.contains('electric')) return 'Electric';
    return 'Gas';
  }

  static String _normalizeAcType(dynamic raw) {
    final s = (raw ?? '').toString().toLowerCase();
    if (s.contains('window')) return 'Window';
    if (s.contains('central')) return 'Central';
    return 'Split';
  }

  static Future<Map<String, dynamic>> _householdToDart(
    Map<String, dynamic> row,
  ) async {
    final id = row['household_id'] as String;

    final billRows = await _client
        .from('Bill')
        .select()
        .eq('household_id', id)
        .order('createdAt', ascending: false);

    final bills = billRows
        .map<Map<String, dynamic>>(
          (b) => {
            'id': b['bill_id'],
            'title': b['title'] ?? '',
            'month': b['month'] ?? '',
            'year': b['year'] ?? '',
            'usage': '${b['consumption'] ?? 0} kWh',
            'consumption': b['consumption'] ?? 0,
            'price': '${b['price'] ?? 0}',
          },
        )
        .toList();

    return {
      'id': id,
      'homeName': row['homeName'] ?? '',
      'housingType': row['housingType'],
      'residents': row['numberOfResidents']?.toString() ?? '1',
      'homeSize': row['homeSize'] ?? '',
      'region': row['region'],
      'insulation': (row['hasInsulation'] == true) ? 'Yes' : 'No',
      'cookingFuel': row['cookingFuel'],
      'acType': row['acType'],
      'bills': bills,
      'appliedAdvice': row['appliedAdvice'] ?? [],
      'behaviorAnswers': row['behaviorAnswers'] ?? {},
      'behaviorCompleted': row['behaviorCompleted'] ?? false,
    };
  }

  static Future<List<String>> _syncBills(
    String householdId,
    List<dynamic> bills,
  ) async {
    final existing = await _client
        .from('Bill')
        .select('bill_id')
        .eq('household_id', householdId);

    final existingIds = existing.map((b) => b['bill_id'] as String).toSet();
    final keptIds = <String>{};
    final insertedIds = <String>[];

    for (final raw in bills) {
      final b = Map<String, dynamic>.from(raw as Map);
      final id = b['id'] as String?;

      final payload = {
        'household_id': householdId,
        'title': b['title'],
        'month': b['month'],
        'year': b['year']?.toString(),
        'consumption': _numOrNull(b['consumption']),
        'price': _numOrNull(b['price']),
      };

      if (id != null && existingIds.contains(id)) {
        keptIds.add(id);
        await _client.from('Bill').update(payload).eq('bill_id', id);
      } else {
        final inserted = await _client
            .from('Bill')
            .insert(payload)
            .select('bill_id')
            .single();
        insertedIds.add(inserted['bill_id'] as String);
      }
    }

    final toDelete = existingIds.difference(keptIds);
    for (final id in toDelete) {
      // NOTE: with the current RLS policies this deletes nothing (there is no
      // DELETE policy on "Bill"). Do not add one without replacing this loop by
      // an explicit "delete bill" action: a stale local list would otherwise
      // delete bills that were added from another screen or device.
      await _client.from('Bill').delete().eq('bill_id', id);
    }
    return insertedIds;
  }
  // ─────────────────────────────────────────────────────────────
  // USAGE (behavior info, per household)
  // ─────────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>?> getUsage(String householdId) async {
    final row = await _client
        .from('Usage')
        .select()
        .eq('household_id', householdId)
        .maybeSingle();

    return row;
  }

  static Future<void> saveUsage(
    String householdId,
    Map<String, dynamic> data,
  ) async {
    final existing = await _client
        .from('Usage')
        .select('usage_id')
        .eq('household_id', householdId)
        .maybeSingle();

    final payload = {
      'household_id': householdId,
      'last_updated': DateTime.now().toUtc().toIso8601String(),
      'applies_energy_tips': data['applies_energy_tips'],
      'willing_to_upgrade_appliance': data['willing_to_upgrade_appliance'],
      'energy_saving_interest': data['energy_saving_interest'],
      'energy_price_pressure': data['energy_price_pressure'],
      'home_improvement_interest': data['home_improvement_interest'],
      'encouraged_by_family': data['encouraged_by_family'],
      'cooling_alternatives': data['cooling_alternatives'],
      'ac_off_when_leaving': data['ac_off_when_leaving'],
      'home_occupancy_time': data['home_occupancy_time'],
      'ac_operating_times': data['ac_operating_times'],
    };

    if (existing != null) {
      await _client
          .from('Usage')
          .update(payload)
          .eq('household_id', householdId);
    } else {
      await _client.from('Usage').insert(payload);
    }
  }

  static num? _numOrNull(dynamic v) {
    if (v == null) return null;
    if (v is num) return v;
    return num.tryParse(v.toString());
  }

  // ─────────────────────────────────────────────────────────────
  // ADVICE
  // ─────────────────────────────────────────────────────────────

  static Future<List<Map<String, dynamic>>> getAdvice({
    String? householdId,
    bool? onlyApplied,
    // Advice is generated per bill. With true, only the newest bill that has
    // advice is returned, so each month's advice doesn't pile up on screen.
    bool latestBillOnly = false,
  }) async {
    final userId = _client.auth.currentUser?.id;
    if (userId == null) return [];

    String? hid = householdId;
    if (hid == null) {
      final home = await getSelectedHome();
      hid = home?['id'] as String?;
    }
    if (hid == null) return [];

    // 1. Get bill ids for this household
    final billRows = await _client
        .from('Bill')
        .select('bill_id')
        .eq('household_id', hid)
        .order('createdAt', ascending: false);

    final billIds = billRows.map((b) => b['bill_id'] as String).toList();
    if (billIds.isEmpty) return [];

    // 2. Get advice for those bills
    var query = _client.from('Advice').select().inFilter('bill_id', billIds);

    if (onlyApplied != null) {
      query = query.eq('isApplied', onlyApplied);
    }

    final rows = await query;

    if (latestBillOnly) {
      for (final billId in billIds) {
        // billIds is newest-first
        final forBill = rows.where((r) => r['bill_id'] == billId).toList();
        if (forBill.isNotEmpty) {
          return forBill.map<Map<String, dynamic>>(_adviceToDart).toList();
        }
      }
      return [];
    }

    return rows.map<Map<String, dynamic>>(_adviceToDart).toList();
  }

  /// Mark advice as applied (Yes) or not applied (No).
  static Future<Map<String, dynamic>> setAdviceApplied(
    String adviceId,
    bool applied,
  ) async {
    final row = await _client
        .from('Advice')
        .update({
          'isApplied': applied,
          'appliedDate': applied
              ? DateTime.now().toUtc().toIso8601String()
              : null,
        })
        .eq('adviceID', adviceId)
        .select()
        .single();

    return _adviceToDart(row);
  }

  /// Adapter: raw Supabase row → Flutter-friendly map.
  /// Only place that knows the real column names.
  static Map<String, dynamic> _adviceToDart(Map<String, dynamic> row) {
    return {
      'id': row['adviceID'],
      'title': row['adviceTitle'] ?? '',
      'content': row['processedAdvice'] ?? '',
      'category': row['adviceCategory'] ?? 'general',
      'isApplied': row['isApplied'] == true,
      'appliedDate': row['appliedDate'],
      'billId': row['bill_id'],
    };
  }
}
