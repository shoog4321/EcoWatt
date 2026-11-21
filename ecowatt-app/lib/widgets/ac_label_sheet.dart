import 'dart:async';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../advice_api.dart';
import '../home_data.dart';
import 'ecowatt_widgets.dart';

/// Opens the AC energy-label scanner as a bottom sheet (no separate page).
/// The result is only shown, never saved.
Future<void> showAcLabelSheet(BuildContext context) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    backgroundColor: Colors.white,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => const _AcLabelSheet(),
  );
}

/// Grade -> colour and plain-language meaning (SASO label, A = most efficient).
class AcGradeInfo {
  final Color color;
  final String title;
  final String meaning;

  const AcGradeInfo(this.color, this.title, this.meaning);

  static AcGradeInfo of(String? grade) {
    switch (grade) {
      case 'A':
        return const AcGradeInfo(
          Color(0xFF15803D),
          'Very efficient',
          'One of the most efficient grades: it uses the least electricity for its cooling power.',
        );
      case 'B':
        return const AcGradeInfo(
          Color(0xFF16A34A),
          'Efficient',
          'Uses less electricity than most air conditioners of the same size.',
        );
      case 'C':
        return const AcGradeInfo(
          Color(0xFF65A30D),
          'Good efficiency',
          'Better than average for its size.',
        );
      case 'D':
        return const AcGradeInfo(
          Color(0xFFCA8A04),
          'Average efficiency',
          'In the middle of the scale. Higher grades of the same size use less electricity.',
        );
      case 'E':
        return const AcGradeInfo(
          Color(0xFFEA580C),
          'Below average',
          'Uses more electricity than most air conditioners of the same size.',
        );
      case 'F':
      case 'G':
        return const AcGradeInfo(
          Color(0xFFDC2626),
          'Low efficiency',
          'Among the least efficient grades: it uses noticeably more electricity for the same cooling.',
        );
      default:
        return const AcGradeInfo(
          ecowattGray,
          'Grade not read',
          'The grade arrow could not be read. Check the coloured arrow on your label (A is best).',
        );
    }
  }
}

class _AcLabelSheet extends StatefulWidget {
  const _AcLabelSheet();

  @override
  State<_AcLabelSheet> createState() => _AcLabelSheetState();
}

class _AcLabelSheetState extends State<_AcLabelSheet> {
  bool _busy = false;
  String? _error;
  Map<String, dynamic>? _result;

  Future<void> _pick(ImageSource source) async {
    XFile? image;
    try {
      image = await ImagePicker().pickImage(source: source, imageQuality: 100);
    } catch (_) {
      setState(
        () => _error = source == ImageSource.camera
            ? 'The camera is not available on this device. Choose a photo instead.'
            : 'Could not open your photos.',
      );
      return;
    }
    if (image == null) return;

    setState(() {
      _busy = true;
      _error = null;
      _result = null;
    });
    try {
      final bytes = await image.readAsBytes();
      final result = await AdviceApi.scanAcLabel(bytes, image.name);
      if (!mounted) return;
      setState(() {
        if (result['success'] == true) {
          _result = result;
        } else {
          _error = (result['message'] ?? 'We could not read this label.')
              .toString();
        }
      });
    } on AdviceApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      debugPrint('AC label scan failed: ${e.runtimeType}: $e');
      if (mounted) {
        setState(
          () => _error = e is TimeoutException
              ? 'Reading the label took too long. Please try again with a clear, close-up photo.'
              : 'Could not reach the EcoWatt server. Please try again.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: EdgeInsets.fromLTRB(
        24,
        12,
        24,
        24 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: ecowattLightGray,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              const Expanded(
                child: Text(
                  "Check your AC's energy label",
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w700,
                    color: ecowattDark,
                  ),
                ),
              ),
              IconButton(
                tooltip: 'Close',
                onPressed: _busy ? null : () => Navigator.pop(context),
                icon: const Icon(Icons.close),
              ),
            ],
          ),
          const SizedBox(height: 4),
          const Text(
            'Take a clear, straight photo of the yellow SASO energy label on your air conditioner.',
            style: TextStyle(fontSize: 13, color: ecowattText, height: 1.4),
          ),
          const SizedBox(height: 18),
          if (_busy)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 36),
              child: Column(
                children: [
                  CircularProgressIndicator(color: ecowattGreen),
                  SizedBox(height: 14),
                  Text(
                    'Reading the label…',
                    style: TextStyle(color: ecowattText),
                  ),
                ],
              ),
            )
          else ...[
            if (_error != null) ...[
              _Notice(text: _error!, error: true),
              const SizedBox(height: 14),
            ],
            if (_result != null) ...[
              AcLabelResult(result: _result!),
              const SizedBox(height: 18),
            ],
            Row(
              children: [
                Expanded(
                  child: _PickButton(
                    icon: Icons.photo_camera_outlined,
                    label: 'Take photo',
                    onTap: () => _pick(ImageSource.camera),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _PickButton(
                    icon: Icons.photo_library_outlined,
                    label: _result == null ? 'Choose photo' : 'Scan another',
                    onTap: () => _pick(ImageSource.gallery),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _PickButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _PickButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: onTap,
      icon: Icon(icon, color: ecowattGreen, size: 20),
      label: Text(
        label,
        style: const TextStyle(
          color: ecowattGreen,
          fontWeight: FontWeight.w600,
        ),
      ),
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(48),
        side: const BorderSide(color: ecowattGreen),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }
}

class _Notice extends StatelessWidget {
  final String text;
  final bool error;

  const _Notice({required this.text, this.error = false});

  @override
  Widget build(BuildContext context) {
    final color = error ? const Color(0xFFDC2626) : const Color(0xFFB45309);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: error ? const Color(0xFFFEF2F2) : const Color(0xFFFFFBEB),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: error ? const Color(0xFFFCA5A5) : const Color(0xFFFCD34D),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            error ? Icons.error_outline : Icons.info_outline,
            color: color,
            size: 20,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: TextStyle(color: color, fontSize: 13, height: 1.35),
            ),
          ),
        ],
      ),
    );
  }
}

class AcLabelResult extends StatelessWidget {
  final Map<String, dynamic> result;

  const AcLabelResult({super.key, required this.result});

  static double? _num(dynamic v) =>
      v is num ? v.toDouble() : double.tryParse('${v ?? ''}');

  /// Label values as printed: up to 2 decimals, no trailing zeros (14.05, 15.0 -> 15, 5.46).
  static String _trim(double v) {
    if (v == v.roundToDouble()) return formatInt(v);
    return v
        .toStringAsFixed(2)
        .replaceFirst(RegExp(r'0+$'), '')
        .replaceFirst(RegExp(r'\.$'), '');
  }

  @override
  Widget build(BuildContext context) {
    final grade = result['grade'] as String?;
    final info = AcGradeInfo.of(grade);
    final analysis = result['analysis'] is Map
        ? Map<String, dynamic>.from(result['analysis'] as Map)
        : const <String, dynamic>{};
    final appliance =
        (analysis['appliance'] ?? result['appliance_type'] ?? 'Air conditioner')
            .toString();
    final meaning = (analysis['grade_meaning'] ?? info.meaning).toString();
    final tip = analysis['tip']?.toString();
    final btu = _num(result['cooling_capacity_btu_h']);
    final kw = _num(result['cooling_capacity_kw']);
    final eff = _num(result['efficiency_value']);
    final metric = (result['efficiency_metric'] ?? '').toString();
    final annual = _num(result['annual_kwh']);
    final brand = (result['brand'] ?? '').toString().trim();
    final model = (result['model_number'] ?? '').toString().trim();

    String? capacityExtra;
    if (kw != null || btu != null) {
      capacityExtra = [
        if (kw != null) '${_trim(kw)} kW',
        if (btu != null) 'about ${(btu / 12000 * 2).round() / 2} ton',
      ].join(' · ');
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'EcoWatt Appliance Analysis',
          style: TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w700,
            color: ecowattDark,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'Appliance: $appliance',
          style: const TextStyle(fontSize: 13, color: ecowattText),
        ),
        const SizedBox(height: 12),

        // Efficiency grade + "What does this mean?"
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: info.color.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: info.color.withValues(alpha: 0.35)),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 64,
                height: 64,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: info.color,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Text(
                  grade ?? '?',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      grade == null
                          ? 'Efficiency Grade: not detected'
                          : 'Efficiency Grade: $grade',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: info.color,
                      ),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'What does this mean?',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: ecowattGray,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      meaning,
                      style: const TextStyle(
                        fontSize: 13,
                        color: ecowattText,
                        height: 1.35,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),

        const _SectionTitle('Energy Information'),
        _Row(
          icon: Icons.bolt_outlined,
          label: 'Annual Energy Consumption',
          value: annual == null ? null : '${formatInt(annual)} kWh/year',
          note: annual == null
              ? null
              : '${analysis['annual_kwh_explanation'] ?? ''} '
                    '(About ${formatInt(annual / 12)} kWh a month.)',
        ),
        _Row(
          icon: Icons.ac_unit,
          label: 'Cooling Capacity',
          value: btu == null
              ? (kw == null ? null : '${_trim(kw)} kW')
              : '${formatInt(btu)} BTU/h',
          note: btu == null && kw == null
              ? null
              : [
                  if (btu != null && capacityExtra != null) capacityExtra,
                  (analysis['cooling_capacity_explanation'] ??
                          'This indicates how much cooling the AC can provide.')
                      .toString(),
                ].join('. '),
        ),

        if (eff != null || brand.isNotEmpty || model.isNotEmpty) ...[
          const SizedBox(height: 4),
          const _SectionTitle('More from the label'),
          if (eff != null)
            _Row(
              icon: Icons.speed_outlined,
              label: metric.isEmpty
                  ? 'Efficiency value'
                  : 'Efficiency ($metric)',
              value: '${_trim(eff)}  (higher is better)',
            ),
          if (brand.isNotEmpty || model.isNotEmpty)
            _Row(
              icon: Icons.sell_outlined,
              label: 'Brand and model',
              value: [brand, model].where((s) => s.isNotEmpty).join(' · '),
            ),
        ],

        if (tip != null) ...[
          const SizedBox(height: 4),
          const _SectionTitle('Our Tip'),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: ecowattLight,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: ecowattGreen.withValues(alpha: 0.3)),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.lightbulb_outline,
                  color: ecowattGreen,
                  size: 20,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    tip,
                    style: const TextStyle(
                      fontSize: 13,
                      color: ecowattDark,
                      height: 1.4,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
        const SizedBox(height: 14),
        _Notice(
          text: result['complete'] == true
              ? 'Values were read automatically. Please compare them with your label.'
              : 'Some values could not be read. Please check them on your label.',
        ),
      ],
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String text;

  const _SectionTitle(this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 15,
          fontWeight: FontWeight.w700,
          color: ecowattDark,
        ),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  final IconData icon;
  final String label;
  final String? value;
  final String? note; // plain-language explanation under the value

  const _Row({
    required this.icon,
    required this.label,
    required this.value,
    this.note,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: const BoxDecoration(
              color: ecowattLight,
              shape: BoxShape.circle,
            ),
            child: Icon(icon, size: 19, color: ecowattGreen),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: const TextStyle(fontSize: 12, color: ecowattGray),
                ),
                const SizedBox(height: 2),
                Text(
                  value ?? 'Not readable – check your label',
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: value == null
                        ? FontWeight.w400
                        : FontWeight.w600,
                    color: value == null ? ecowattGray : ecowattDark,
                    height: 1.35,
                  ),
                ),
                if (note != null && note!.trim().isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    note!.trim(),
                    style: const TextStyle(
                      fontSize: 12.5,
                      color: ecowattText,
                      height: 1.4,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
