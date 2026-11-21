import 'package:flutter/material.dart';

import '../home_data.dart';
import '../widgets/ac_label_sheet.dart';
import '../widgets/ecowatt_widgets.dart';

const _savingGreen = Color(0xFF86EFAC);
const _aboveRed = Color(0xFFDC2626);

/// Home: latest bill, 6-month trend and comparison with similar homes, all
/// from the selected home's bills and the backend's rule-engine analysis.
/// Reloads every time the tab is opened (MainScreen recreates this widget).
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late Future<HomeData> _future = HomeData.load();

  Future<void> _reload() async {
    final f = HomeData.load();
    setState(() => _future = f);
    await f;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ecowattPageBg,
      body: RefreshIndicator(
        onRefresh: _reload,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          child: Column(
            children: [
              FutureBuilder<HomeData>(
                future: _future,
                builder: (context, snap) => EcowattPageHeader(
                  title: snap.hasData ? snap.data!.greeting : 'Welcome!',
                  subtitle: "Let's track your energy usage",
                ),
              ),
              EcowattOverlap(
                child: FutureBuilder<HomeData>(
                  future: _future,
                  builder: (context, snap) {
                    if (snap.connectionState != ConnectionState.done) {
                      return const _WhiteCard(
                        child: SizedBox(
                          height: 120,
                          child: Center(
                            child: CircularProgressIndicator(
                              color: ecowattGreen,
                            ),
                          ),
                        ),
                      );
                    }
                    if (snap.hasError) {
                      return _WhiteCard(
                        child: _Message(
                          icon: Icons.cloud_off,
                          text:
                              'Could not load your data. Pull down to try again.',
                        ),
                      );
                    }
                    final data = snap.data!;
                    if (data.latest == null) {
                      return Column(
                        children: [
                          _WhiteCard(
                            child: _Message(
                              icon: Icons.receipt_long_outlined,
                              text:
                                  'Add your first electricity bill in the Bills tab '
                                  'to see your consumption trend and how you compare.',
                            ),
                          ),
                          const SizedBox(height: 20),
                          const _AcLabelCard(),
                          const SizedBox(height: 20),
                          const _AdviceCard(),
                        ],
                      );
                    }
                    return Column(
                      children: [
                        _BillCard(data: data),
                        const SizedBox(height: 20),
                        _TrendCard(data: data),
                        const SizedBox(height: 20),
                        _CompareCard(data: data),
                        const SizedBox(height: 20),
                        const _AcLabelCard(),
                        const SizedBox(height: 20),
                        const _AdviceCard(),
                        const SizedBox(height: 12),
                      ],
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Message extends StatelessWidget {
  final IconData icon;
  final String text;

  const _Message({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: ecowattGray),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            text,
            style: const TextStyle(
              fontSize: 13,
              color: ecowattText,
              height: 1.4,
            ),
          ),
        ),
      ],
    );
  }
}

String _sar(double v) =>
    v == v.roundToDouble() ? formatInt(v) : v.toStringAsFixed(2);

class _BillCard extends StatelessWidget {
  final HomeData data;

  const _BillCard({required this.data});

  @override
  Widget build(BuildContext context) {
    final latest = data.latest!;
    final previous = data.previous;
    final diff = previous == null ? null : latest.priceSar - previous.priceSar;
    final pct = (previous == null || previous.priceSar == 0)
        ? null
        : diff! / previous.priceSar * 100;
    final down = (diff ?? 0) <= 0;
    final color = down ? ecowattGreen : _aboveRed;

    return _WhiteCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                'Latest Bill · ${latest.periodLabel}',
                style: const TextStyle(color: ecowattGray, fontSize: 14),
              ),
              const Spacer(),
              if (pct != null)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 7,
                  ),
                  decoration: BoxDecoration(
                    color: down
                        ? const Color(0xFFDCFCE7)
                        : const Color(0xFFFEE2E2),
                    borderRadius: BorderRadius.circular(50),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        down ? Icons.trending_down : Icons.trending_up,
                        size: 14,
                        color: color,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        changeBadgeText(pct),
                        style: TextStyle(
                          color: color,
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                _sar(latest.priceSar),
                style: const TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.w800,
                  color: Colors.black,
                ),
              ),
              const SizedBox(width: 6),
              const Padding(
                padding: EdgeInsets.only(bottom: 5),
                child: Text(
                  'SAR',
                  style: TextStyle(fontSize: 16, color: ecowattText),
                ),
              ),
              const Spacer(),
              Padding(
                padding: const EdgeInsets.only(bottom: 5),
                child: Text(
                  '${formatInt(latest.kwh)} kWh',
                  style: const TextStyle(fontSize: 14, color: ecowattText),
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Text(
            previous == null
                ? 'Add more bills to compare with previous months'
                : 'vs ${previous.periodLabel}:  ${diff! > 0
                      ? '+'
                      : diff < 0
                      ? '-'
                      : ''}${_sar(diff.abs())} SAR',
            style: const TextStyle(fontSize: 13, color: ecowattText),
          ),
        ],
      ),
    );
  }
}

class _TrendCard extends StatefulWidget {
  final HomeData data;

  const _TrendCard({required this.data});

  @override
  State<_TrendCard> createState() => _TrendCardState();
}

class _TrendCardState extends State<_TrendCard> {
  int? selectedIndex;

  @override
  Widget build(BuildContext context) {
    final bills = widget.data.bills;
    final saving = widget.data.savingSar;
    final selected = selectedIndex == null ? null : bills[selectedIndex!];

    return _WhiteCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            bills.length >= 6
                ? '6-Month Consumption Trend'
                : 'Consumption Trend',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 14),
          const Row(
            children: [
              Icon(Icons.circle, size: 10, color: ecowattGreen),
              SizedBox(width: 4),
              Text(
                'Actual Consumption',
                style: TextStyle(fontSize: 12, color: ecowattText),
              ),
              SizedBox(width: 14),
              Icon(Icons.circle, size: 10, color: _savingGreen),
              SizedBox(width: 4),
              Text(
                'Potential Saving',
                style: TextStyle(fontSize: 12, color: ecowattText),
              ),
            ],
          ),
          const SizedBox(height: 16),
          LayoutBuilder(
            builder: (context, constraints) {
              final width = constraints.maxWidth;
              return GestureDetector(
                onTapDown: (details) {
                  final i = _LineChartPainter.indexAt(
                    details.localPosition.dx,
                    width,
                    bills.length,
                  );
                  setState(() => selectedIndex = selectedIndex == i ? null : i);
                },
                child: Stack(
                  children: [
                    SizedBox(
                      height: 230,
                      width: width,
                      child: CustomPaint(
                        painter: _LineChartPainter(
                          selectedIndex: selectedIndex,
                          consumption: [for (final b in bills) b.kwh],
                          optimized: [for (final b in bills) b.optimizedKwh],
                          months: [for (final b in bills) b.monthLabel],
                        ),
                      ),
                    ),
                    if (selected != null)
                      Positioned(
                        top: 55,
                        left: 0,
                        right: 0,
                        child: Center(
                          child: Container(
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(10),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withValues(alpha: 0.12),
                                  blurRadius: 10,
                                  offset: const Offset(0, 4),
                                ),
                              ],
                            ),
                            child: Text(
                              '${selected.periodLabel}\n'
                              'Consumption: ${formatInt(selected.kwh)} kWh\n'
                              'Potential: ${formatInt(selected.optimizedKwh)} kWh',
                              style: const TextStyle(
                                fontSize: 14,
                                color: ecowattGreen,
                                height: 1.7,
                              ),
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              );
            },
          ),
          const SizedBox(height: 12),
          if (saving != null && saving > 0)
            Text.rich(
              TextSpan(
                text: 'Reduce your next bill by about ',
                style: const TextStyle(fontSize: 13, color: ecowattText),
                children: [
                  TextSpan(
                    text: '${_sar(saving)} SAR/month ',
                    style: const TextStyle(
                      color: ecowattGreen,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const TextSpan(text: 'with our personalized advice'),
                ],
              ),
            )
          else
            const Text(
              'Potential savings appear once your latest bill has been analyzed.',
              style: TextStyle(fontSize: 13, color: ecowattText),
            ),
        ],
      ),
    );
  }
}

class _CompareCard extends StatefulWidget {
  final HomeData data;

  const _CompareCard({required this.data});

  @override
  State<_CompareCard> createState() => _CompareCardState();
}

class _CompareCardState extends State<_CompareCard> {
  String? selectedBar;

  @override
  Widget build(BuildContext context) {
    final latest = widget.data.latest!;
    final similar = latest.similarHomesKwh;
    final pct = latest.comparisonPct;
    final groupParts = [
      widget.data.housingType,
      widget.data.region,
    ].where((s) => s != null && s.isNotEmpty).join(' homes in ');

    return _WhiteCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'How You Compare',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
          ),
          if (latest.hasComparison) ...[
            const SizedBox(height: 4),
            Text(
              '${latest.periodLabel} vs similar ${groupParts.isEmpty ? 'homes' : groupParts}',
              style: const TextStyle(fontSize: 12, color: ecowattGray),
            ),
            const SizedBox(height: 18),
            LayoutBuilder(
              builder: (context, constraints) {
                final width = constraints.maxWidth;
                return GestureDetector(
                  onTapDown: (details) {
                    final tapped = details.localPosition.dx < width / 2
                        ? 'home'
                        : 'similar';
                    setState(
                      () => selectedBar = selectedBar == tapped ? null : tapped,
                    );
                  },
                  child: Stack(
                    children: [
                      SizedBox(
                        height: 190,
                        width: width,
                        child: CustomPaint(
                          painter: _BarChartPainter(
                            homeKwh: latest.kwh,
                            similarKwh: similar!,
                          ),
                        ),
                      ),
                      if (selectedBar != null)
                        Positioned(
                          top: 35,
                          left: 0,
                          right: 0,
                          child: Center(
                            child: _ChartTooltip(
                              title: selectedBar == 'home'
                                  ? 'Your Home'
                                  : 'Similar Homes',
                              value:
                                  'consumption : '
                                  '${formatInt(selectedBar == 'home' ? latest.kwh : similar)} kWh',
                            ),
                          ),
                        ),
                    ],
                  ),
                );
              },
            ),
            const SizedBox(height: 12),
            if (pct != null) _comparisonText(pct),
          ] else ...[
            const SizedBox(height: 14),
            _Message(
              icon: Icons.bar_chart,
              text: widget.data.housingType == 'Other'
                  ? 'There is no national baseline for this housing type, so a comparison is not available.'
                  : 'The comparison with similar homes appears once your latest bill (${latest.periodLabel}) has been analyzed.',
            ),
          ],
        ],
      ),
    );
  }

  Widget _comparisonText(double pct) {
    if (pct.abs() < 0.5) {
      return const Text(
        "You're using about the same as similar homes",
        style: TextStyle(fontSize: 13, color: ecowattText),
      );
    }
    final less = pct < 0;
    final (highlight, tail) = comparisonWording(pct);
    return Text.rich(
      TextSpan(
        text: "You're using ",
        style: const TextStyle(fontSize: 13, color: ecowattText),
        children: [
          TextSpan(
            text: highlight,
            style: TextStyle(
              color: less ? ecowattGreen : _aboveRed,
              fontWeight: FontWeight.w700,
            ),
          ),
          TextSpan(text: tail),
        ],
      ),
    );
  }
}

class _ChartTooltip extends StatelessWidget {
  final String title;
  final String value;

  const _ChartTooltip({required this.title, required this.value});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 200,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.12),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Text.rich(
        TextSpan(
          text: '$title\n',
          style: const TextStyle(
            color: Colors.black,
            fontSize: 16,
            height: 1.7,
          ),
          children: [
            TextSpan(
              text: value,
              style: const TextStyle(color: ecowattGreen, fontSize: 15),
            ),
          ],
        ),
      ),
    );
  }
}

/// Opens the AC energy-label scanner (bottom sheet, results only).
class _AcLabelCard extends StatelessWidget {
  const _AcLabelCard();

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () => showAcLabelSheet(context),
        child: Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFE5E7EB)),
          ),
          child: const Row(
            children: [
              CircleAvatar(
                radius: 24,
                backgroundColor: ecowattLight,
                child: Icon(Icons.qr_code_scanner, color: ecowattGreen),
              ),
              SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      "Check your AC's energy label",
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: ecowattDark,
                      ),
                    ),
                    SizedBox(height: 4),
                    Text(
                      'Scan the label to see its efficiency grade, size and yearly use.',
                      style: TextStyle(
                        fontSize: 13,
                        color: ecowattText,
                        height: 1.35,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: ecowattGray),
            ],
          ),
        ),
      ),
    );
  }
}

class _AdviceCard extends StatelessWidget {
  const _AdviceCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: ecowattGreen,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.12),
            blurRadius: 10,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.lightbulb_outline, color: Colors.white, size: 28),
          SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Get Personalized Energy\nAdvice',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    height: 1.25,
                  ),
                ),
                SizedBox(height: 10),
                Text(
                  'Visit the Advice page to receive AI-powered recommendations tailored to your household energy consumption patterns.',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                    height: 1.35,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _WhiteCard extends StatelessWidget {
  final Widget child;

  const _WhiteCard({required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5E7EB)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: child,
    );
  }
}

class _LineChartPainter extends CustomPainter {
  static const left = 38.0;
  static const right = 8.0;

  final int? selectedIndex;
  final List<double> consumption;
  final List<double> optimized;
  final List<String> months;

  _LineChartPainter({
    required this.selectedIndex,
    required this.consumption,
    required this.optimized,
    required this.months,
  });

  static double xAt(int index, double width, int count) {
    final chartWidth = width - left - right;
    if (count <= 1) return left + chartWidth / 2;
    return left + chartWidth / (count - 1) * index;
  }

  /// The data point closest to a tap at [dx].
  static int indexAt(double dx, double width, int count) {
    var best = 0;
    for (var i = 1; i < count; i++) {
      if ((xAt(i, width, count) - dx).abs() <
          (xAt(best, width, count) - dx).abs()) {
        best = i;
      }
    }
    return best;
  }

  @override
  void paint(Canvas canvas, Size size) {
    const top = 10.0;
    const bottom = 36.0;
    final chartHeight = size.height - top - bottom;
    final maxY = niceAxisMax(
      [...consumption, ...optimized].fold<double>(0, (a, b) => a > b ? a : b),
    );

    final gridPaint = Paint()
      ..color = const Color(0xFFE5E7EB)
      ..strokeWidth = 1;
    final axisPaint = Paint()
      ..color = const Color(0xFFCBD5E1)
      ..strokeWidth = 1.2;
    final line1Paint = Paint()
      ..color = ecowattGreen
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke;
    final line2Paint = Paint()
      ..color = _savingGreen
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke;

    double yValue(double value) =>
        top + chartHeight - (value / maxY) * chartHeight;
    double xValue(int index) => xAt(index, size.width, months.length);

    final tp = TextPainter(textDirection: TextDirection.ltr);

    for (var k = 4; k >= 0; k--) {
      final label = maxY * k / 4;
      final y = yValue(label);
      canvas.drawLine(
        Offset(left, y),
        Offset(size.width - right, y),
        gridPaint,
      );
      tp.text = TextSpan(
        text: axisLabel(label),
        style: const TextStyle(fontSize: 10, color: ecowattGray),
      );
      tp.layout();
      tp.paint(canvas, Offset(0, y - 7));
    }

    canvas.drawLine(
      Offset(left, top),
      Offset(left, top + chartHeight),
      axisPaint,
    );
    canvas.drawLine(
      Offset(left, top + chartHeight),
      Offset(size.width - right, top + chartHeight),
      axisPaint,
    );

    Path buildPath(List<double> data) {
      final path = Path();
      for (var i = 0; i < data.length; i++) {
        final point = Offset(xValue(i), yValue(data[i]));
        i == 0
            ? path.moveTo(point.dx, point.dy)
            : path.lineTo(point.dx, point.dy);
      }
      return path;
    }

    canvas.drawPath(buildPath(optimized), line2Paint);
    canvas.drawPath(buildPath(consumption), line1Paint);

    for (var i = 0; i < months.length; i++) {
      canvas.drawCircle(
        Offset(xValue(i), yValue(optimized[i])),
        5,
        Paint()..color = _savingGreen,
      );
      canvas.drawCircle(
        Offset(xValue(i), yValue(consumption[i])),
        5,
        Paint()..color = ecowattGreen,
      );

      tp.text = TextSpan(
        text: months[i],
        style: const TextStyle(fontSize: 11, color: ecowattGray),
      );
      tp.layout();
      tp.paint(canvas, Offset(xValue(i) - tp.width / 2, size.height - 22));
    }

    if (selectedIndex != null) {
      final x = xValue(selectedIndex!);
      canvas.drawLine(
        Offset(x, top),
        Offset(x, top + chartHeight),
        Paint()
          ..color = const Color(0xFFCBD5E1)
          ..strokeWidth = 1,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _LineChartPainter oldDelegate) =>
      oldDelegate.selectedIndex != selectedIndex ||
      oldDelegate.consumption != consumption ||
      oldDelegate.optimized != optimized;
}

class _BarChartPainter extends CustomPainter {
  final double homeKwh;
  final double similarKwh;

  _BarChartPainter({required this.homeKwh, required this.similarKwh});

  @override
  void paint(Canvas canvas, Size size) {
    const left = 38.0;
    const top = 10.0;
    const bottom = 32.0;
    final chartWidth = size.width - left - 8;
    final chartHeight = size.height - top - bottom;
    final maxY = niceAxisMax(homeKwh > similarKwh ? homeKwh : similarKwh);

    final gridPaint = Paint()
      ..color = const Color(0xFFE5E7EB)
      ..strokeWidth = 1;
    final axisPaint = Paint()
      ..color = const Color(0xFFCBD5E1)
      ..strokeWidth = 1.2;
    final homePaint = Paint()..color = ecowattGreen;
    final similarPaint = Paint()..color = _savingGreen;

    final tp = TextPainter(textDirection: TextDirection.ltr);

    double yValue(double value) =>
        top + chartHeight - (value / maxY) * chartHeight;

    for (var k = 4; k >= 0; k--) {
      final label = maxY * k / 4;
      final y = yValue(label);
      canvas.drawLine(Offset(left, y), Offset(size.width - 8, y), gridPaint);
      tp.text = TextSpan(
        text: axisLabel(label),
        style: const TextStyle(fontSize: 10, color: ecowattGray),
      );
      tp.layout();
      tp.paint(canvas, Offset(0, y - 7));
    }

    canvas.drawLine(
      Offset(left, top),
      Offset(left, top + chartHeight),
      axisPaint,
    );
    canvas.drawLine(
      Offset(left, top + chartHeight),
      Offset(size.width - 8, top + chartHeight),
      axisPaint,
    );

    const barWidth = 60.0;
    final homeCenter = left + chartWidth * 0.27;
    final similarCenter = left + chartWidth * 0.73;

    void bar(double center, double value, Paint paint, String label) {
      final y = yValue(value);
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(
            center - barWidth / 2,
            y,
            barWidth,
            top + chartHeight - y,
          ),
          const Radius.circular(8),
        ),
        paint,
      );
      tp.text = TextSpan(
        text: label,
        style: const TextStyle(fontSize: 10, color: ecowattGray),
      );
      tp.layout();
      tp.paint(canvas, Offset(center - tp.width / 2, size.height - 18));
    }

    bar(homeCenter, homeKwh, homePaint, 'Your Home');
    bar(similarCenter, similarKwh, similarPaint, 'Similar Homes');
  }

  @override
  bool shouldRepaint(covariant _BarChartPainter oldDelegate) =>
      oldDelegate.homeKwh != homeKwh || oldDelegate.similarKwh != similarKwh;
}
