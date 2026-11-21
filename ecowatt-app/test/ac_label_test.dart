import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_application_1/widgets/ac_label_sheet.dart';

void main() {
  testWidgets('AC label result shows the grade and friendly values', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(375 * 3, 900 * 3); // iPhone SE width
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: AcLabelResult(
              result: {
                'success': true,
                'grade': 'D',
                'grade_arabic': 'د',
                'cooling_capacity_btu_h': 18600,
                'cooling_capacity_kw': 14.05,
                'efficiency_metric': 'EER',
                'efficiency_value': 15.05,
                'annual_kwh': 6049,
                'brand': 'GREE',
                'model_number': 'GWC18AVDXF-D3NTA1A/O',
                'complete': true,
                'analysis': {
                  'appliance': 'Air conditioner',
                  'grade_meaning':
                      'This AC is less energy-efficient than models rated A, B, or C.',
                  'annual_kwh_explanation':
                      'This represents the estimated annual electricity consumption under the '
                      "label's specified testing conditions. Actual consumption may vary depending on usage and "
                      'operating conditions.',
                  'cooling_capacity_explanation':
                      'This indicates how much cooling the AC can provide.',
                  'tip':
                      "Consider the AC's efficiency grade and annual electricity consumption when choosing a model. "
                      'Make sure its cooling capacity meets your cooling needs.',
                },
              },
            ),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    // the notebook's report sections and wording
    expect(find.text('EcoWatt Appliance Analysis'), findsOneWidget);
    expect(find.text('Appliance: Air conditioner'), findsOneWidget);
    expect(find.text('Efficiency Grade: D'), findsOneWidget);
    expect(find.text('What does this mean?'), findsOneWidget);
    expect(
      find.text(
        'This AC is less energy-efficient than models rated A, B, or C.',
      ),
      findsOneWidget,
    );
    expect(find.text('Energy Information'), findsOneWidget);
    expect(find.text('6,049 kWh/year'), findsOneWidget);
    expect(find.textContaining('specified testing conditions'), findsOneWidget);
    expect(find.text('18,600 BTU/h'), findsOneWidget);
    expect(find.textContaining('14.05 kW · about 1.5 ton'), findsOneWidget);
    expect(
      find.textContaining('how much cooling the AC can provide'),
      findsOneWidget,
    );
    expect(find.text('Our Tip'), findsOneWidget);
    expect(
      find.textContaining(
        'Make sure its cooling capacity meets your cooling needs.',
      ),
      findsOneWidget,
    );
    expect(
      find.textContaining('15.05'),
      findsOneWidget,
    ); // label values are not rounded
    expect(find.text('GREE · GWC18AVDXF-D3NTA1A/O'), findsOneWidget);
  });

  test('grades map to colours and plain-language meanings', () {
    expect(AcGradeInfo.of('A').title, 'Very efficient');
    expect(AcGradeInfo.of('F').title, 'Low efficiency');
    expect(AcGradeInfo.of('G').title, 'Low efficiency');
    expect(AcGradeInfo.of(null).title, 'Grade not read');
  });
}
