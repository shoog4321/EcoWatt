import 'dart:math' as math;

import 'package:supabase_flutter/supabase_flutter.dart';

import 'user_storage.dart';

const _monthAbbr = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/// One bill of the selected home, with the numbers the backend's rule engine
/// stored on it (null / 0 until the bill has been analysed).
class BillPoint {
  final String id;
  final int year;
  final int month;
  final double kwh;
  final double priceSar;
  final double? similarHomesKwh; // Bill.regionAverageKwh
  final double?
  comparisonPct; // Bill.comparisonPercentage (+ = above similar homes)
  final double savingKwh; // Bill.potentialSavingKwh

  const BillPoint({
    required this.id,
    required this.year,
    required this.month,
    required this.kwh,
    required this.priceSar,
    required this.similarHomesKwh,
    required this.comparisonPct,
    required this.savingKwh,
  });

  String get monthLabel => _monthAbbr[month - 1];
  String get periodLabel => '$monthLabel $year';

  /// Consumption after the potential saving ("Potential Saving" line).
  double get optimizedKwh => math.max(0, kwh - savingKwh);

  bool get hasComparison => similarHomesKwh != null && similarHomesKwh! > 0;
}

/// Everything the home screen shows, loaded from Supabase.
class HomeData {
  final List<BillPoint> bills; // oldest -> newest, at most 6
  final double? savingSar; // latest bill, from the rule-engine analysis
  final String? region;
  final String? housingType;
  final String firstName;
  final bool
  hasAnyBill; // any saved bill, valid or not (false = brand-new user)

  const HomeData({
    required this.bills,
    this.savingSar,
    this.region,
    this.housingType,
    this.firstName = '',
    this.hasAnyBill = false,
  });

  /// "Welcome, Sara!" for a new user, "Welcome back, Sara!" once they have bills.
  String get greeting {
    final name = firstName.isEmpty ? '' : ', $firstName';
    return hasAnyBill ? 'Welcome back$name!' : 'Welcome$name!';
  }

  BillPoint? get latest => bills.isEmpty ? null : bills.last;
  BillPoint? get previous => bills.length < 2 ? null : bills[bills.length - 2];

  static SupabaseClient get _client => Supabase.instance.client;

  static Future<HomeData> load() async {
    final firstName = await _firstName();
    final home = await UserStorage.getSelectedHome();
    if (home == null) return HomeData(bills: const [], firstName: firstName);

    final rows = await _client
        .from('Bill')
        .select(
          'bill_id,month,year,consumption,price,regionAverageKwh,'
          'comparisonPercentage,potentialSavingKwh,createdAt',
        )
        .eq('household_id', home['id'])
        .order('createdAt', ascending: false);

    // One bill per period (newest entry wins), skipping bills the backend
    // would reject as unreadable or inconsistent with the tariff.
    final byPeriod = <int, BillPoint>{};
    for (final r in rows) {
      final month = parseMonth(r['month']);
      final year = int.tryParse('${r['year'] ?? ''}'.trim());
      final kwh = _num(r['consumption']);
      final price = _num(r['price']);
      if (month == null || year == null || kwh == null || price == null) {
        continue;
      }
      if (kwh <= 0 || price <= 0 || tariffInconsistent(kwh, price)) continue;

      final key = year * 12 + month;
      if (byPeriod.containsKey(key)) continue;
      final similar = _num(r['regionAverageKwh']);
      byPeriod[key] = BillPoint(
        id: r['bill_id'] as String,
        year: year,
        month: month,
        kwh: kwh,
        priceSar: price,
        similarHomesKwh: similar,
        // the column defaults to 0, so it only means something once analysed
        comparisonPct: similar != null ? _num(r['comparisonPercentage']) : null,
        savingKwh: _num(r['potentialSavingKwh']) ?? 0,
      );
    }

    final keys = byPeriod.keys.toList()..sort();
    final bills = keys
        .skip(math.max(0, keys.length - 6))
        .map((k) => byPeriod[k]!)
        .toList();

    double? savingSar;
    if (bills.isNotEmpty) {
      final job = await _client
          .from('advice_jobs')
          .select('analysis')
          .eq('bill_id', bills.last.id)
          .maybeSingle();
      final analysis = job?['analysis'];
      if (analysis is Map) savingSar = _num(analysis['saving_sar']);
    }

    return HomeData(
      bills: bills,
      savingSar: savingSar,
      region: home['region']?.toString(),
      housingType: home['housingType']?.toString(),
      firstName: firstName,
      hasAnyBill: rows.isNotEmpty,
    );
  }

  static Future<String> _firstName() async {
    final userId = _client.auth.currentUser?.id;
    if (userId == null) return '';
    final row = await _client
        .from('User')
        .select('firstName')
        .eq('id', userId)
        .maybeSingle();
    return (row?['firstName'] ?? '').toString().trim();
  }

  static int? parseMonth(dynamic value) {
    final s = '${value ?? ''}'.trim().toLowerCase();
    final n = int.tryParse(s);
    if (n != null) return (n >= 1 && n <= 12) ? n : null;
    if (s.length < 3) return null;
    final i = _monthAbbr.indexWhere((m) => s.startsWith(m.toLowerCase()));
    return i < 0 ? null : i + 1;
  }

  /// Same rule as the backend (app/bills.py): residential tariff 0.18 / 0.30
  /// SAR per kWh, +15% VAT, +15 SAR meter fee; reject when the price is off by
  /// more than 200 SAR AND more than 25%.
  static double expectedCostSar(double kwh) {
    final energy = math.min(kwh, 6000) * 0.18 + math.max(kwh - 6000, 0) * 0.30;
    return energy * 1.15 + 15;
  }

  static bool tariffInconsistent(double kwh, double price) {
    final expected = expectedCostSar(kwh);
    final dev = (price - expected).abs();
    return dev > 200 && dev / expected > 0.25;
  }

  static double? _num(dynamic v) {
    if (v == null) return null;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString());
  }
}

/// "1,234" style integer formatting without pulling in intl.
String formatInt(double v) {
  final s = v.round().abs().toString();
  final out = StringBuffer(v < 0 ? '-' : '');
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) out.write(',');
    out.write(s[i]);
  }
  return out.toString();
}

/// Upper bound for a chart axis: a round number just above [max].
double niceAxisMax(double max) {
  if (max <= 0) return 100;
  final raw = max * 1.1;
  final magnitude = math
      .pow(10, (math.log(raw) / math.ln10).floor())
      .toDouble();
  // steps whose quarters are round numbers (axis labels at 1/4, 1/2, 3/4, max)
  for (final step in [1, 2, 4, 6, 8, 10]) {
    if (step * magnitude >= raw) return step * magnitude;
  }
  return 10 * magnitude;
}

/// Short axis label: 750, 2.5k, 10k.
String axisLabel(double v) {
  if (v >= 1000) {
    final k = v / 1000;
    return '${k == k.roundToDouble() ? k.toStringAsFixed(0) : k.toStringAsFixed(1)}k';
  }
  return v.toStringAsFixed(0);
}

/// Wording for "How You Compare": (highlighted part, rest of the sentence).
/// From double the usage upwards a multiple reads better than a percentage
/// ("about 2.9× the usage of" instead of "193.0% more than").
(String, String) comparisonWording(double pct) {
  if (pct >= 100) {
    return (
      'about ${(1 + pct / 100).toStringAsFixed(1)}× the usage',
      ' of similar homes',
    );
  }
  return (
    '${pct.abs().toStringAsFixed(1)}% ${pct < 0 ? 'less' : 'more'}',
    ' than similar homes',
  );
}

/// Text of the "Latest Bill" badge (change in price vs the previous bill).
/// From double the price upwards a multiple reads better ("2.0×" instead of "104.7%").
String changeBadgeText(double pct) => pct >= 100
    ? '${(1 + pct / 100).toStringAsFixed(1)}×'
    : '${pct.abs().toStringAsFixed(1)}%';
