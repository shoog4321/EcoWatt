import 'package:flutter/material.dart';
import '../widgets/ecowatt_widgets.dart';
import 'behavior_information_screen.dart';
import '../user_storage.dart';

class EnergyInfoScreen extends StatefulWidget {
  final String firstName;
  final String lastName;
  final String email;
  final String phone;
  final String password;

  final String homeName;
  final String housingType;
  final String residents;
  final String homeSize;

  const EnergyInfoScreen({
    super.key,
    required this.firstName,
    required this.lastName,
    required this.email,
    required this.phone,
    required this.password,
    required this.homeName,
    required this.housingType,
    required this.residents,
    required this.homeSize,
  });

  @override
  State<EnergyInfoScreen> createState() => _EnergyInfoScreenState();
}

class _EnergyInfoScreenState extends State<EnergyInfoScreen> {
  String? selectedCity;
  String? selectedInsulation;
  String? selectedCookingType;

  String? selectedAcType;

  bool get canFinish =>
      selectedCity != null &&
      selectedAcType != null &&
      selectedInsulation != null &&
      selectedCookingType != null;

  @override
  Widget build(BuildContext context) {
    return EcowattScaffold(
      showBack: true,
      stepText: 'Step 2 of 2',
      progress: 1,
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(32, 24, 32, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Energy Usage',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: ecowattDark,
              ),
            ),

            const SizedBox(height: 8),

            const Text(
              'Final step to personalize your experience',
              style: TextStyle(fontSize: 16, color: ecowattText),
            ),

            const SizedBox(height: 32),

            const Text(
              'City',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
            ),

            const SizedBox(height: 8),

            DropdownButtonFormField<String>(
              // key: re-create the field when the value is set from code (e.g. by the bill scanner)
              key: ValueKey(selectedCity),
              initialValue: selectedCity,
              decoration: InputDecoration(
                filled: true,
                fillColor: const Color(0xFFF3F3F5),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: BorderSide.none,
                ),
              ),
              hint: const Text('Select your city'),
              items:
                  [
                        'Riyadh',
                        'Qassim',
                        'Eastern Region',
                        'Makkah',
                        'Madinah',
                        'Hail',
                        'Tabuk',
                        'Northern Borders',
                        'Aseer',
                        'Jazan',
                        'Najran',
                        'Al-Baha',
                        'Al-Jouf',
                      ]
                      .map(
                        (city) =>
                            DropdownMenuItem(value: city, child: Text(city)),
                      )
                      .toList(),
              onChanged: (value) {
                setState(() {
                  selectedCity = value;
                });
              },
            ),

            const SizedBox(height: 24),

            const Text(
              'What type of air conditioner do you have?',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
            ),

            const SizedBox(height: 12),

            OptionTile(
              text: 'Split Air Conditioner',
              selected: selectedAcType == 'Split Air Conditioner',
              onTap: () {
                setState(() {
                  selectedAcType = 'Split Air Conditioner';
                });
              },
            ),

            const SizedBox(height: 12),

            OptionTile(
              text: 'Window Air Conditioner',
              selected: selectedAcType == 'Window Air Conditioner',
              onTap: () {
                setState(() {
                  selectedAcType = 'Window Air Conditioner';
                });
              },
            ),

            const SizedBox(height: 12),

            OptionTile(
              text: 'Central Air Conditioner',
              selected: selectedAcType == 'Central Air Conditioner',
              onTap: () {
                setState(() {
                  selectedAcType = 'Central Air Conditioner';
                });
              },
            ),
            const Text(
              'Does your home have insulation?',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
            ),

            const SizedBox(height: 12),

            Row(
              children: [
                Expanded(
                  child: OptionTile(
                    text: 'Yes',
                    selected: selectedInsulation == 'Yes',
                    onTap: () {
                      setState(() {
                        selectedInsulation = 'Yes';
                      });
                    },
                  ),
                ),

                const SizedBox(width: 12),

                Expanded(
                  child: OptionTile(
                    text: 'No',
                    selected: selectedInsulation == 'No',
                    onTap: () {
                      setState(() {
                        selectedInsulation = 'No';
                      });
                    },
                  ),
                ),
              ],
            ),

            const SizedBox(height: 24),

            const Text(
              'Cooking Type',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
            ),

            const SizedBox(height: 12),

            Row(
              children: [
                Expanded(
                  child: OptionTile(
                    text: 'Gas',
                    selected: selectedCookingType == 'Gas',
                    onTap: () {
                      setState(() {
                        selectedCookingType = 'Gas';
                      });
                    },
                  ),
                ),

                const SizedBox(width: 12),

                Expanded(
                  child: OptionTile(
                    text: 'Electric',
                    selected: selectedCookingType == 'Electric',
                    onTap: () {
                      setState(() {
                        selectedCookingType = 'Electric';
                      });
                    },
                  ),
                ),
              ],
            ),

            const SizedBox(height: 24),

            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFFF0FDF4),
                border: Border.all(color: const Color(0xFF86EFAC)),
                borderRadius: BorderRadius.circular(14),
              ),
              child: const Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    Icons.check_circle_outline,
                    color: ecowattGreen,
                    size: 24,
                  ),

                  SizedBox(width: 14),

                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Almost there!',
                          style: TextStyle(
                            color: ecowattDark,
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                          ),
                        ),

                        SizedBox(height: 8),

                        Text(
                          "We'll use this information to provide personalized insights and recommendations for your household.",
                          style: TextStyle(
                            color: ecowattText,
                            fontSize: 14,
                            height: 1.35,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            Opacity(
              opacity: canFinish ? 1 : 0.5,
              child: EcowattButton(
                text: 'Complete Setup',
                onPressed: canFinish
                    ? () async {
                        final firstHomeId =
                            'home_${DateTime.now().millisecondsSinceEpoch}';

                        final firstHome = {
                          'id': firstHomeId,
                          'homeName': widget.homeName,
                          'housingType': widget.housingType,
                          'residents': widget.residents,
                          'homeSize': widget.homeSize,
                          'region': selectedCity,
                          'insulation': selectedInsulation,
                          'cookingFuel': selectedCookingType,
                          'acType': selectedAcType,

                          // These will be used later
                          // for home-specific data.
                          'bills': [],
                          'appliedAdvice': [],
                          'behaviorAnswers': {},
                          'behaviorCompleted': false,
                        };

                        try {
                          await UserStorage.saveUser(
                            email: widget.email,
                            data: {
                              'firstName': widget.firstName,
                              'lastName': widget.lastName,
                              'email': widget.email,
                              'phone': widget.phone,
                              'password': widget.password,
                              'selectedHomeId': firstHomeId,
                              'homes': [firstHome],
                            },
                          );
                        } catch (e) {
                          if (!context.mounted) return;
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text('Signup failed: $e'),
                              duration: const Duration(seconds: 8),
                            ),
                          );
                          return;
                        }
                        if (!context.mounted) return;

                        Navigator.pushReplacement(
                          context,
                          MaterialPageRoute(
                            builder: (_) => const BehaviorInformationScreen(
                              fromRegistration: true,
                            ),
                          ),
                        );
                      }
                    : () {},
              ),
            ),
          ],
        ),
      ),
    );
  }
}
