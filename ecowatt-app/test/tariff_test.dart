import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_application_1/home_data.dart';

void main() {
  test('expected cost follows the SEC residential tariff', () {
    // the real Aug 2026 bill: 2903.14 kWh, 612.46 SAR (its meter fee is 10 SAR, the formula uses 15)
    expect(HomeData.expectedCostSar(2903.14), closeTo(615.9, 0.1));
    expect(HomeData.expectedCostSar(6000), closeTo(1257.0, 0.1));
    expect(
      HomeData.expectedCostSar(7000),
      closeTo(1257.0 + 1000 * 0.30 * 1.15, 0.1),
    );
  });

  test('typos are caught, real bills pass', () {
    expect(HomeData.tariffInconsistent(2903.14, 612.46), isFalse); // real bill
    expect(HomeData.tariffInconsistent(6000, 1260), isFalse);
    expect(
      HomeData.tariffInconsistent(1580, 600),
      isTrue,
    ); // 1580 kWh should be ~342 SAR
    expect(HomeData.tariffInconsistent(1.07, 1007), isTrue); // kWh typed wrong
    expect(HomeData.tariffInconsistent(72119.91, 657.32), isTrue);
  });

  test('month names and numbers are parsed', () {
    expect(HomeData.parseMonth('August'), 8);
    expect(HomeData.parseMonth('aug'), 8);
    expect(HomeData.parseMonth('12'), 12);
    expect(HomeData.parseMonth('13'), isNull);
  });

  test('chart axis tops divide into round quarters', () {
    expect(niceAxisMax(2903), 4000); // labels 1k, 2k, 3k, 4k
    expect(niceAxisMax(4351), 6000); // 1.5k, 3k, 4.5k, 6k
    expect(niceAxisMax(600), 800);
    expect(axisLabel(1500), '1.5k');
    expect(axisLabel(750), '750');
  });

  test("comparison wording switches to a multiple from double the usage", () {
    expect(comparisonWording(193.01), (
      "about 2.9× the usage",
      " of similar homes",
    ));
    expect(comparisonWording(100), (
      "about 2.0× the usage",
      " of similar homes",
    ));
    expect(comparisonWording(43.23), ("43.2% more", " than similar homes"));
    expect(comparisonWording(-19.58), ("19.6% less", " than similar homes"));
    expect(changeBadgeText(104.67), "2.0×");
    expect(changeBadgeText(250), "3.5×");
    expect(changeBadgeText(43.2), "43.2%");
    expect(changeBadgeText(-12.5), "12.5%");
  });
}
