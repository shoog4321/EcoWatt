import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_application_1/widgets/ecowatt_widgets.dart';

void main() {
  // Question 7's longest answer overflowed a fixed-height tile on phone widths.
  testWidgets(
    'long questionnaire options wrap instead of overflowing on a small phone',
    (tester) async {
      tester.view.physicalSize = const Size(
        320 * 3,
        640 * 3,
      ); // narrower than an iPhone SE
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Padding(
              padding: EdgeInsets.all(24),
              child: Column(
                children: [
                  OptionTile(
                    text: 'No, I rely almost exclusively on air-conditioning',
                    selected: true,
                  ),
                  OptionTile(text: 'Yes'),
                ],
              ),
            ),
          ),
        ),
      );

      expect(
        tester.takeException(),
        isNull,
      ); // a RenderFlex overflow would be reported here
      final tall = tester.getSize(find.byType(OptionTile).first).height;
      final short = tester.getSize(find.byType(OptionTile).last).height;
      expect(
        short,
        greaterThanOrEqualTo(50),
      ); // short options keep the original height
      expect(tall, greaterThan(short)); // the long one grew onto a second line
    },
  );
}
