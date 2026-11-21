import 'package:flutter/material.dart';
import '../widgets/ecowatt_widgets.dart';
import 'energy_info_screen.dart';
import 'package:flutter/services.dart';

class HouseholdInformationScreen extends StatefulWidget {
  final String firstName;
  final String lastName;
  final String email;
  final String phone;
  final String password;

  const HouseholdInformationScreen({
    super.key,
    required this.firstName,
    required this.lastName,
    required this.email,
    required this.phone,
    required this.password,
  });

  @override
  State<HouseholdInformationScreen> createState() =>
      _HouseholdInformationScreenState();
}

class _HouseholdInformationScreenState
    extends State<HouseholdInformationScreen> {
  final homeNameController = TextEditingController();
  final residentsController = TextEditingController();
  final homeSizeController = TextEditingController();

  String? selectedHouseType;

  bool get canContinue =>
      homeNameController.text.trim().isNotEmpty &&
      selectedHouseType != null &&
      residentsController.text.trim().isNotEmpty &&
      homeSizeController.text.trim().isNotEmpty;

  @override
  Widget build(BuildContext context) {
    return EcowattScaffold(
      showBack: true,
      stepText: 'Step 1 of 2',
      progress: 0.5,
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(32, 24, 32, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Household Information',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: ecowattDark,
              ),
            ),

            const SizedBox(height: 8),

            const Text(
              'Help us understand your living situation',
              style: TextStyle(fontSize: 16, color: ecowattText),
            ),

            const SizedBox(height: 32),

            const Text(
              'Home Name',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
            ),

            const SizedBox(height: 8),

            TextField(
              controller: homeNameController,
              onChanged: (_) {
                setState(() {});
              },
              decoration: InputDecoration(
                hintText: 'e.g. Family Home',
                filled: true,
                fillColor: const Color(0xFFF3F3F5),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: BorderSide.none,
                ),
              ),
            ),

            const SizedBox(height: 24),

            const Text(
              'House Type',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
            ),

            const SizedBox(height: 12),

            OptionTile(
              text: 'Villa',
              selected: selectedHouseType == 'Villa',
              onTap: () => setState(() => selectedHouseType = 'Villa'),
            ),

            const SizedBox(height: 12),

            OptionTile(
              text: 'Floor In Villa',
              selected: selectedHouseType == 'Floor In Villa',
              onTap: () => setState(() => selectedHouseType = 'Floor In Villa'),
            ),

            const SizedBox(height: 12),

            OptionTile(
              text: 'Apartment',
              selected: selectedHouseType == 'Apartment',
              onTap: () => setState(() => selectedHouseType = 'Apartment'),
            ),

            const SizedBox(height: 12),

            OptionTile(
              text: 'Traditional House',
              selected: selectedHouseType == 'Traditional House',
              onTap: () =>
                  setState(() => selectedHouseType = 'Traditional House'),
            ),

            const SizedBox(height: 12),

            OptionTile(
              text: 'Floor In Traditional House',
              selected: selectedHouseType == 'Floor In Traditional House',
              onTap: () => setState(
                () => selectedHouseType = 'Floor In Traditional House',
              ),
            ),

            const SizedBox(height: 24),

            const Text(
              'Home Residents',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
            ),

            const SizedBox(height: 8),

            TextField(
              controller: residentsController,
              onChanged: (_) {
                setState(() {});
              },
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: InputDecoration(
                hintText: 'Enter number of residents',
                filled: true,
                fillColor: const Color(0xFFF3F3F5),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: BorderSide.none,
                ),
              ),
            ),

            const SizedBox(height: 24),

            const Text(
              'Home Size (m²)',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
            ),

            const SizedBox(height: 4),

            const Text(
              'Enter the built-up area only, excluding the yard or outdoor spaces.',
              style: TextStyle(fontSize: 12, color: ecowattGray),
            ),

            const SizedBox(height: 8),

            TextField(
              controller: homeSizeController,
              onChanged: (_) {
                setState(() {});
              },
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: InputDecoration(
                hintText: 'Enter built-up area in square meters',
                filled: true,
                fillColor: const Color(0xFFF3F3F5),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: BorderSide.none,
                ),
              ),
            ),

            const SizedBox(height: 24),

            Opacity(
              opacity: canContinue ? 1 : 0.5,
              child: EcowattButton(
                text: 'Continue',
                onPressed: canContinue
                    ? () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) => EnergyInfoScreen(
                              firstName: widget.firstName,
                              lastName: widget.lastName,
                              email: widget.email,
                              phone: widget.phone,
                              password: widget.password,
                              homeName: homeNameController.text.trim(),
                              housingType: selectedHouseType!,
                              residents: residentsController.text.trim(),
                              homeSize: homeSizeController.text.trim(),
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

  @override
  void dispose() {
    homeNameController.dispose();
    residentsController.dispose();
    homeSizeController.dispose();
    super.dispose();
  }
}
