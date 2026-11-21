import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../widgets/ecowatt_widgets.dart';
import 'welcome_screen.dart';
import 'behavior_information_screen.dart';
import '../user_storage.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  String firstName = '';
  String lastName = '';
  String email = '';
  String phone = '';

  List<Map<String, dynamic>> homes = [];
  Map<String, dynamic>? selectedHome;

  static const List<String> regions = [
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
  ];

  static const List<String> housingOptions = [
    'Villa',
    'Floor In Villa',
    'Apartment',
    'Traditional House',
    'Floor In Traditional House',
  ];

  static const List<String> acOptions = [
    'Split Air Conditioner',
    'Window Air Conditioner',
    'Central Air Conditioner',
  ];

  static const List<String> cookingOptions = ['Natural Gas', 'Electric'];

  @override
  void initState() {
    super.initState();
    loadUserData();
  }

  String _normalizeCookingFuel(String value) {
    final v = value.trim().toLowerCase();

    if (v == 'gas' || v == 'natural gas') {
      return 'Natural Gas';
    }

    if (v == 'electric' || v == 'electricity') {
      return 'Electric';
    }

    return value.trim();
  }

  String _normalizeAcType(String value) {
    final v = value.trim().toLowerCase();

    if (v.contains('split')) {
      return 'Split Air Conditioner';
    }

    if (v.contains('window')) {
      return 'Window Air Conditioner';
    }

    if (v.contains('central')) {
      return 'Central Air Conditioner';
    }

    return value.trim();
  }

  Future<void> loadUserData() async {
    final user = await UserStorage.getCurrentUser();
    final loadedHomes = await UserStorage.getHomes();
    final currentHome = await UserStorage.getSelectedHome();

    if (user == null) return;
    if (!mounted) return;

    setState(() {
      firstName = user['firstName'] ?? '';
      lastName = user['lastName'] ?? '';
      email = user['email'] ?? '';
      phone = user['phone'] ?? '';

      homes = loadedHomes;
      selectedHome = currentHome;
    });
  }

  Future<void> _selectHome(Map<String, dynamic> home) async {
    await UserStorage.selectHome(home['id']);

    await loadUserData();

    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('${home['homeName']} is now selected')),
    );
  }

  void _showHomeSelector() {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Select Home',
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w700,
                    color: ecowattDark,
                  ),
                ),

                const SizedBox(height: 16),

                ...homes.map((home) {
                  final isSelected = selectedHome?['id'] == home['id'];

                  return Container(
                    margin: const EdgeInsets.only(bottom: 10),
                    decoration: BoxDecoration(
                      border: Border.all(
                        color: isSelected ? ecowattGreen : ecowattLightGray,
                      ),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: ListTile(
                      leading: Container(
                        width: 42,
                        height: 42,
                        decoration: BoxDecoration(
                          color: isSelected
                              ? const Color(0xFFEFFDF4)
                              : const Color(0xFFF3F4F6),
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          Icons.home_outlined,
                          color: isSelected ? ecowattGreen : ecowattText,
                        ),
                      ),
                      title: Text(
                        home['homeName'] ?? 'Home',
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                      subtitle: Text(
                        '${home['region'] ?? ''} • ${home['housingType'] ?? ''}',
                      ),
                      trailing: isSelected
                          ? const Icon(Icons.check_circle, color: ecowattGreen)
                          : null,
                      onTap: () async {
                        Navigator.pop(context);
                        await _selectHome(home);
                      },
                    ),
                  );
                }),

                const SizedBox(height: 6),

                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: OutlinedButton.icon(
                    onPressed: () {
                      Navigator.pop(context);
                      _openHomeDialog(isNewHome: true);
                    },
                    icon: const Icon(Icons.add, color: ecowattGreen),
                    label: const Text(
                      'Add New Home',
                      style: TextStyle(
                        color: ecowattGreen,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: ecowattGreen),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void _openHomeDialog({required bool isNewHome}) {
    final formKey = GlobalKey<FormState>();

    final current = isNewHome ? <String, dynamic>{} : selectedHome ?? {};

    final homeNameController = TextEditingController(
      text: current['homeName'] ?? '',
    );

    final residentsController = TextEditingController(
      text: current['residents'] ?? '',
    );

    final homeSizeController = TextEditingController(
      text: current['homeSize'] ?? '',
    );

    String? tempRegion = (current['region'] ?? '').toString().isNotEmpty
        ? current['region']
        : null;

    String? tempHousing = (current['housingType'] ?? '').toString().isNotEmpty
        ? current['housingType']
        : null;

    String? tempInsulation = (current['insulation'] ?? '').toString().isNotEmpty
        ? current['insulation']
        : null;

    final normalizedCooking = _normalizeCookingFuel(
      current['cookingFuel'] ?? '',
    );

    String? tempCooking = cookingOptions.contains(normalizedCooking)
        ? normalizedCooking
        : null;

    final normalizedAc = _normalizeAcType(current['acType'] ?? '');

    String? tempAc = acOptions.contains(normalizedAc) ? normalizedAc : null;

    showDialog(
      context: context,
      builder: (context) {
        return Dialog(
          insetPadding: const EdgeInsets.symmetric(horizontal: 18),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          child: StatefulBuilder(
            builder: (context, setDialogState) {
              return SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: Form(
                  key: formKey,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              isNewHome
                                  ? 'Add New Home'
                                  : 'Edit Household Details',
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),

                          IconButton(
                            onPressed: () => Navigator.pop(context),
                            icon: const Icon(Icons.close),
                          ),
                        ],
                      ),

                      const SizedBox(height: 14),

                      const _EditLabel('Home Name'),

                      _EditTextField(
                        controller: homeNameController,
                        validator: (value) {
                          if (value == null || value.trim().isEmpty) {
                            return 'Home name is required';
                          }

                          return null;
                        },
                      ),

                      const _EditLabel('Region'),

                      _EditDropdown(
                        value: tempRegion,
                        items: regions,
                        validator: (value) {
                          if (value == null || value.isEmpty) {
                            return 'Region is required';
                          }

                          return null;
                        },
                        onChanged: (value) {
                          setDialogState(() {
                            tempRegion = value;
                          });
                        },
                      ),

                      const _EditLabel('Housing Type'),

                      _EditDropdown(
                        value: tempHousing,
                        items: housingOptions,
                        validator: (value) {
                          if (value == null || value.isEmpty) {
                            return 'Housing type is required';
                          }

                          return null;
                        },
                        onChanged: (value) {
                          setDialogState(() {
                            tempHousing = value;
                          });
                        },
                      ),

                      const _EditLabel('Built-up Area (m²)'),

                      const Text(
                        'Enter the built-up area only, excluding the yard or outdoor spaces.',
                        style: TextStyle(fontSize: 12, color: ecowattGray),
                      ),

                      const SizedBox(height: 6),

                      _EditTextField(
                        controller: homeSizeController,
                        keyboardType: TextInputType.number,
                        inputFormatters: [
                          FilteringTextInputFormatter.digitsOnly,
                        ],
                        validator: (value) {
                          final text = value?.trim() ?? '';
                          final number = int.tryParse(text);

                          if (text.isEmpty) {
                            return 'Built-up area is required';
                          }

                          if (number == null || number <= 0) {
                            return 'Enter a valid built-up area';
                          }

                          return null;
                        },
                      ),

                      const _EditLabel('Residents'),

                      _EditTextField(
                        controller: residentsController,
                        keyboardType: TextInputType.number,
                        inputFormatters: [
                          FilteringTextInputFormatter.digitsOnly,
                        ],
                        validator: (value) {
                          final text = value?.trim() ?? '';
                          final number = int.tryParse(text);

                          if (text.isEmpty) {
                            return 'Residents is required';
                          }

                          if (number == null || number <= 0) {
                            return 'Residents must be at least 1';
                          }

                          return null;
                        },
                      ),

                      const _EditLabel('Insulation'),

                      _EditDropdown(
                        value: tempInsulation,
                        items: const ['Yes', 'No'],
                        validator: (value) {
                          if (value == null || value.isEmpty) {
                            return 'Insulation is required';
                          }

                          return null;
                        },
                        onChanged: (value) {
                          setDialogState(() {
                            tempInsulation = value;
                          });
                        },
                      ),

                      const _EditLabel('AC Type'),

                      _EditDropdown(
                        value: tempAc,
                        items: acOptions,
                        validator: (value) {
                          if (value == null || value.isEmpty) {
                            return 'AC type is required';
                          }

                          return null;
                        },
                        onChanged: (value) {
                          setDialogState(() {
                            tempAc = value;
                          });
                        },
                      ),

                      const _EditLabel('Cooking Fuel'),

                      _EditDropdown(
                        value: tempCooking,
                        items: cookingOptions,
                        validator: (value) {
                          if (value == null || value.isEmpty) {
                            return 'Cooking fuel is required';
                          }

                          return null;
                        },
                        onChanged: (value) {
                          setDialogState(() {
                            tempCooking = value;
                          });
                        },
                      ),

                      const SizedBox(height: 20),

                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton(
                              onPressed: () => Navigator.pop(context),
                              child: const Text('Cancel'),
                            ),
                          ),

                          const SizedBox(width: 10),

                          Expanded(
                            child: ElevatedButton.icon(
                              style: ElevatedButton.styleFrom(
                                backgroundColor: ecowattGreen,
                                foregroundColor: Colors.white,
                              ),
                              onPressed: () async {
                                if (!formKey.currentState!.validate()) {
                                  return;
                                }

                                final home = {
                                  'id': isNewHome
                                      ? 'home_${DateTime.now().millisecondsSinceEpoch}'
                                      : current['id'],
                                  'homeName': homeNameController.text.trim(),
                                  'region': tempRegion!,
                                  'housingType': tempHousing!,
                                  'homeSize': homeSizeController.text.trim(),
                                  'residents': residentsController.text.trim(),
                                  'insulation': tempInsulation!,
                                  'acType': tempAc!,
                                  'cookingFuel': tempCooking!,
                                  'bills': current['bills'] ?? [],
                                  'appliedAdvice':
                                      current['appliedAdvice'] ?? [],
                                  'behaviorAnswers':
                                      current['behaviorAnswers'] ?? {},
                                  'behaviorCompleted':
                                      current['behaviorCompleted'] ?? false,
                                };

                                try {
                                  if (isNewHome) {
                                    await UserStorage.addHome(home);
                                  } else {
                                    await UserStorage.updateHome(home);
                                  }
                                } catch (e) {
                                  if (!context.mounted) return;
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text('Failed to save home: $e'),
                                    ),
                                  );
                                  return;
                                }

                                if (!context.mounted) return;
                                Navigator.pop(context);
                                await loadUserData();
                              },
                              icon: Icon(
                                isNewHome ? Icons.add : Icons.save,
                                size: 18,
                              ),
                              label: Text(
                                isNewHome ? 'Add Home' : 'Save Changes',
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final home = selectedHome;

    final region = home?['region']?.toString() ?? '';
    final housingType = home?['housingType']?.toString() ?? '';
    final residents = home?['residents']?.toString() ?? '';
    final homeSize = home?['homeSize']?.toString() ?? '';
    final insulation = home?['insulation']?.toString() ?? '';

    final acType = _normalizeAcType(home?['acType']?.toString() ?? '');

    final cookingFuel = _normalizeCookingFuel(
      home?['cookingFuel']?.toString() ?? '',
    );

    final behaviorCompleted = home?['behaviorCompleted'] == true;

    return Scaffold(
      backgroundColor: ecowattPageBg,
      body: ListView(
        padding: EdgeInsets.zero,
        children: [
          EcowattPageHeader(
            title: 'Profile',
            children: [
              const SizedBox(height: 20),

              Row(
                children: [
                  Container(
                    width: 64,
                    height: 64,
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.18),
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: Colors.white.withValues(alpha: 0.35),
                        width: 1.5,
                      ),
                    ),
                    child: const Icon(
                      Icons.person_outline,
                      color: Colors.white,
                      size: 34,
                    ),
                  ),

                  const SizedBox(width: 16),

                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '$firstName $lastName',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 20,
                            fontWeight: FontWeight.w700,
                          ),
                        ),

                        if (email.isNotEmpty) ...[
                          const SizedBox(height: 5),
                          Row(
                            children: [
                              const Icon(
                                Icons.email_outlined,
                                color: Colors.white70,
                                size: 15,
                              ),
                              const SizedBox(width: 6),
                              Expanded(
                                child: Text(
                                  email,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    color: Colors.white70,
                                    fontSize: 13,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ],

                        if (phone.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Row(
                            children: [
                              const Icon(
                                Icons.phone_outlined,
                                color: Colors.white70,
                                size: 15,
                              ),
                              const SizedBox(width: 6),
                              Text(
                                phone,
                                style: const TextStyle(
                                  color: Colors.white70,
                                  fontSize: 13,
                                ),
                              ),
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ],
          ),

          EcowattOverlap(
            child: Column(
              children: [
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(22),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.10),
                        blurRadius: 10,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: home == null
                      ? const Text('No home added')
                      : Column(
                          children: [
                            Row(
                              children: [
                                Container(
                                  width: 56,
                                  height: 56,
                                  decoration: const BoxDecoration(
                                    color: ecowattGreen,
                                    shape: BoxShape.circle,
                                  ),
                                  child: const Icon(
                                    Icons.home_outlined,
                                    color: Colors.white,
                                    size: 30,
                                  ),
                                ),

                                const SizedBox(width: 14),

                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        home['homeName'] ?? 'Home',
                                        style: const TextStyle(
                                          fontSize: 18,
                                          fontWeight: FontWeight.w700,
                                          color: ecowattDark,
                                        ),
                                      ),

                                      const SizedBox(height: 5),

                                      Text(
                                        '$region • $housingType',
                                        style: const TextStyle(
                                          color: ecowattText,
                                          fontSize: 14,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),

                                IconButton(
                                  onPressed: _showHomeSelector,
                                  icon: const Icon(
                                    Icons.keyboard_arrow_down,
                                    color: ecowattGreen,
                                    size: 30,
                                  ),
                                ),
                              ],
                            ),

                            const SizedBox(height: 16),

                            SizedBox(
                              width: double.infinity,
                              child: OutlinedButton.icon(
                                onPressed: () =>
                                    _openHomeDialog(isNewHome: true),
                                icon: const Icon(
                                  Icons.add,
                                  color: ecowattGreen,
                                ),
                                label: const Text(
                                  'Add New Home',
                                  style: TextStyle(
                                    color: ecowattGreen,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                style: OutlinedButton.styleFrom(
                                  side: const BorderSide(color: ecowattGreen),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                ),

                const SizedBox(height: 20),

                if (home != null && !behaviorCompleted) ...[
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFEF2F2),
                      border: Border.all(color: const Color(0xFFFCA5A5)),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(
                          Icons.error_outline,
                          color: Color(0xFFDC2626),
                          size: 26,
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                'Complete your behavior information',
                                style: TextStyle(
                                  color: ecowattDark,
                                  fontSize: 16,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              const SizedBox(height: 6),
                              const Text(
                                'Help us understand your behavior better to provide more personalized recommendations for this home.',
                                style: TextStyle(
                                  color: ecowattText,
                                  fontSize: 13,
                                  height: 1.4,
                                ),
                              ),
                              const SizedBox(height: 12),
                              GestureDetector(
                                onTap: () async {
                                  await Navigator.push(
                                    context,
                                    MaterialPageRoute(
                                      builder: (_) =>
                                          const BehaviorInformationScreen(),
                                    ),
                                  );
                                  await loadUserData();
                                },
                                child: const Text(
                                  'Complete Information →',
                                  style: TextStyle(
                                    color: Color(0xFFDC2626),
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),
                ],

                const SizedBox(height: 6),

                Row(
                  children: [
                    const Text(
                      'Household Details',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                        color: ecowattDark,
                      ),
                    ),
                    const Spacer(),
                    if (home != null)
                      GestureDetector(
                        onTap: () => _openHomeDialog(isNewHome: false),
                        child: const Text(
                          'Edit',
                          style: TextStyle(
                            color: ecowattGreen,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                  ],
                ),

                const SizedBox(height: 12),

                _ProfileTile(
                  icon: Icons.location_on_outlined,
                  title: 'Region',
                  value: region,
                ),
                _ProfileTile(
                  icon: Icons.home_outlined,
                  title: 'Housing Type',
                  value: housingType,
                ),
                _ProfileTile(
                  icon: Icons.square_foot_outlined,
                  title: 'Built-up Area',
                  value: homeSize.isEmpty ? '' : '$homeSize m²',
                ),
                _ProfileTile(
                  icon: Icons.groups_outlined,
                  title: 'Residents',
                  value: residents,
                ),
                _ProfileTile(
                  icon: Icons.thermostat_outlined,
                  title: 'Insulation',
                  value: insulation,
                ),
                _ProfileTile(
                  icon: Icons.air_outlined,
                  title: 'AC Type',
                  value: acType,
                ),
                _ProfileTile(
                  icon: Icons.kitchen_outlined,
                  title: 'Cooking Fuel',
                  value: cookingFuel,
                ),

                const SizedBox(height: 18),

                const _AboutCard(),

                const SizedBox(height: 22),

                SizedBox(
                  height: 48,
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: () async {
                      await UserStorage.logout();
                      if (!context.mounted) return;
                      Navigator.pushAndRemoveUntil(
                        context,
                        MaterialPageRoute(
                          builder: (_) => const WelcomeScreen(),
                        ),
                        (route) => false,
                      );
                    },
                    icon: const Icon(Icons.logout, color: Colors.red, size: 18),
                    label: const Text(
                      'Log Out',
                      style: TextStyle(
                        color: Colors.red,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: Colors.red),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                  ),
                ),

                const SizedBox(height: 20),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ProfileTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String value;

  const _ProfileTile({
    required this.icon,
    required this.title,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    final shownValue = value.trim().isEmpty ? '-' : value;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: ecowattLightGray),
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 6,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: const BoxDecoration(
              color: Color(0xFFF3F4F6),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, color: ecowattText, size: 22),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(color: ecowattText, fontSize: 13),
                ),
                const SizedBox(height: 4),
                Text(
                  shownValue,
                  style: const TextStyle(
                    color: Colors.black,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
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

class _AboutCard extends StatelessWidget {
  const _AboutCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: ecowattLightGray),
        borderRadius: BorderRadius.circular(14),
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'About EcoWatt',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
          ),
          SizedBox(height: 12),
          Text(
            'EcoWatt is your AI-powered companion for understanding and optimizing electricity consumption. '
            'We help Saudi households make informed energy decisions and reduce costs through awareness and insights.',
            style: TextStyle(color: ecowattText, height: 1.5),
          ),
          SizedBox(height: 16),
          Text(
            'Version 1.0.0',
            style: TextStyle(color: ecowattGray, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _EditLabel extends StatelessWidget {
  final String text;

  const _EditLabel(this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12, bottom: 6),
      child: Text(text, style: const TextStyle(fontWeight: FontWeight.w600)),
    );
  }
}

class _EditTextField extends StatelessWidget {
  final TextEditingController controller;
  final TextInputType? keyboardType;
  final List<TextInputFormatter>? inputFormatters;
  final String? Function(String?)? validator;

  const _EditTextField({
    required this.controller,
    this.keyboardType,
    this.inputFormatters,
    this.validator,
  });

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      keyboardType: keyboardType,
      inputFormatters: inputFormatters,
      validator: validator,
      decoration: InputDecoration(
        filled: true,
        fillColor: const Color(0xFFF3F3F5),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 12,
          vertical: 14,
        ),
        errorMaxLines: 2,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide.none,
        ),
      ),
    );
  }
}

class _EditDropdown extends StatelessWidget {
  final String? value;
  final List<String> items;
  final ValueChanged<String?> onChanged;
  final String? Function(String?)? validator;

  const _EditDropdown({
    required this.value,
    required this.items,
    required this.onChanged,
    this.validator,
  });

  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<String>(
      // key: re-create the field when the value is set from code (e.g. by the bill scanner)
      key: ValueKey(value != null && items.contains(value) ? value : null),
      initialValue: value != null && items.contains(value) ? value : null,
      isExpanded: true,
      validator: validator,
      decoration: InputDecoration(
        filled: true,
        fillColor: const Color(0xFFF3F3F5),
        contentPadding: const EdgeInsets.symmetric(horizontal: 12),
        errorMaxLines: 2,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide.none,
        ),
      ),
      items: items
          .map(
            (item) => DropdownMenuItem<String>(value: item, child: Text(item)),
          )
          .toList(),
      onChanged: onChanged,
    );
  }
}
