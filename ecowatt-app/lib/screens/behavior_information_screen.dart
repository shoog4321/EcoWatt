import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../widgets/ecowatt_widgets.dart';
import '../user_storage.dart';
import 'main_screen.dart';

class BehaviorInformationScreen extends StatefulWidget {
  final bool fromRegistration;

  const BehaviorInformationScreen({super.key, this.fromRegistration = false});

  @override
  State<BehaviorInformationScreen> createState() =>
      _BehaviorInformationScreenState();
}

class _BehaviorInformationScreenState extends State<BehaviorInformationScreen> {
  final PageController _pageController = PageController();

  int currentQuestion = 0;

  final Map<String, dynamic> answers = {};

  final TextEditingController inBuildingHoursController =
      TextEditingController();

  final TextEditingController acHoursController = TextEditingController();

  final List<Map<String, dynamic>> questions = [
    {
      'key': 'applies_energy_tips',
      'question':
          'Do you apply energy-saving tips when using electrical appliances at home?',
      'type': 'bool',
      'options': ['Yes', 'No'],
    },
    {
      'key': 'willing_to_upgrade_appliance',
      'question':
          'Would you be willing to spend some money to replace older appliances with newer, more energy-efficient ones?',
      'type': 'bool',
      'options': ['Yes', 'No'],
    },
    {
      'key': 'energy_saving_interest',
      'question':
          'How interested are you in reducing and rationalizing electricity consumption in your home?',
      'type': 'numeric',
      'options': ['Very interested', 'Somewhat interested', 'Not interested'],
      'values': [3, 2, 1],
    },
    {
      'key': 'energy_price_pressure',
      'question':
          'Do you feel pressure from rising energy prices or electricity bills?',
      'type': 'numeric',
      'options': ['Always', 'Usually', 'Sometimes', 'Never'],
      'values': [4, 3, 2, 1],
    },
    {
      'key': 'home_improvement_interest',
      'question':
          'Would you invest in home improvements, such as better insulation or solar panels, if they reduced your bills?',
      'type': 'numeric',
      'options': ['Always', 'Usually', 'Sometimes', 'Never'],
      'values': [4, 3, 2, 1],
    },
    {
      'key': 'encouraged_by_family',
      'question': 'Do the residents of your house encourage energy saving?',
      'type': 'numeric',
      'options': [
        'Strongly agree',
        'Agree',
        'Neutral',
        'Disagree',
        'Strongly disagree',
      ],
      'values': [5, 4, 3, 2, 1],
    },
    {
      'key': 'cooling_alternatives',
      'question':
          'Do you use any alternatives to air-conditioning for cooling in summer?',
      'type': 'text',
      'options': [
        'Natural ventilation',
        'Electric fans',
        'Desert cooler',
        'More than one of the above',
        'No, I rely almost exclusively on air-conditioning',
        'Other',
      ],
    },
    {
      'key': 'ac_off_when_leaving',
      'question':
          'If you leave your residence for 1 hour, will you turn off your air conditioning?',
      'type': 'numeric',
      'options': ['Always', 'Usually', 'Sometimes', 'Never'],
      'values': [4, 3, 2, 1],
    },
    {
      'key': 'home_occupancy_time',
      'question': "Please indicate your (or your family's) in-building time.",
      'type': 'hours',
    },
    {
      'key': 'ac_operating_times',
      'question':
          'Please indicate the air-conditioning operating times in your residence.',
      'type': 'hours',
    },
  ];

  @override
  void initState() {
    super.initState();
    _loadExistingAnswers();
  }

  Future<void> _loadExistingAnswers() async {
    final home = await UserStorage.getSelectedHome();
    if (home == null) return;

    final homeId = home['id'] as String;
    final usage = await UserStorage.getUsage(homeId);
    if (usage == null) return;

    answers['applies_energy_tips'] = usage['applies_energy_tips'];
    answers['willing_to_upgrade_appliance'] =
        usage['willing_to_upgrade_appliance'];
    answers['energy_saving_interest'] = usage['energy_saving_interest'];
    answers['energy_price_pressure'] = usage['energy_price_pressure'];
    answers['home_improvement_interest'] = usage['home_improvement_interest'];
    answers['encouraged_by_family'] = usage['encouraged_by_family'];
    answers['cooling_alternatives'] = usage['cooling_alternatives'];
    answers['ac_off_when_leaving'] = usage['ac_off_when_leaving'];
    answers['home_occupancy_time'] = usage['home_occupancy_time'];
    answers['ac_operating_times'] = usage['ac_operating_times'];

    if (usage['home_occupancy_time'] != null) {
      inBuildingHoursController.text = usage['home_occupancy_time'].toString();
    }
    if (usage['ac_operating_times'] != null) {
      acHoursController.text = usage['ac_operating_times'].toString();
    }

    if (mounted) setState(() {});
  }

  bool _isCurrentAnswered() {
    final question = questions[currentQuestion];
    final key = question['key'];

    if (question['type'] == 'hours') {
      final controller = key == 'home_occupancy_time'
          ? inBuildingHoursController
          : acHoursController;
      final value = int.tryParse(controller.text.trim());
      return value != null && value >= 0 && value <= 24;
    }

    return answers[key] != null;
  }

  void _selectAnswer(Map<String, dynamic> question, int optionIndex) {
    final key = question['key'];
    final type = question['type'];
    final option = question['options'][optionIndex];

    setState(() {
      if (type == 'bool') {
        answers[key] = option == 'Yes';
      } else if (type == 'numeric') {
        final values = List<int>.from(question['values']);
        answers[key] = values[optionIndex];
      } else {
        answers[key] = option;
      }
    });

    if (currentQuestion < questions.length - 1) {
      Future.delayed(const Duration(milliseconds: 250), () {
        if (!mounted) return;
        _goNext();
      });
    }
  }

  void _goNext() {
    if (!_isCurrentAnswered()) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please answer this question before continuing.'),
        ),
      );
      return;
    }

    final question = questions[currentQuestion];

    if (question['type'] == 'hours') {
      final key = question['key'];
      final controller = key == 'home_occupancy_time'
          ? inBuildingHoursController
          : acHoursController;
      answers[key] = int.tryParse(controller.text.trim());
    }

    if (currentQuestion < questions.length - 1) {
      _pageController.nextPage(
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeInOut,
      );
    } else {
      _saveAndFinish();
    }
  }

  void _goBack() {
    if (currentQuestion > 0) {
      _pageController.previousPage(
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeInOut,
      );
    }
  }

  Future<void> _saveAndFinish() async {
    final home = await UserStorage.getSelectedHome();
    if (home == null) return;

    if (inBuildingHoursController.text.trim().isNotEmpty) {
      answers['home_occupancy_time'] = int.tryParse(
        inBuildingHoursController.text.trim(),
      );
    }
    if (acHoursController.text.trim().isNotEmpty) {
      answers['ac_operating_times'] = int.tryParse(
        acHoursController.text.trim(),
      );
    }

    final homeId = home['id'] as String;

    try {
      await UserStorage.saveUsage(homeId, answers);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Failed to save: $e')));
      return;
    }

    final updatedHome = Map<String, dynamic>.from(home);
    updatedHome['behaviorCompleted'] = true;
    await UserStorage.updateHome(updatedHome);

    if (!mounted) return;

    if (widget.fromRegistration) {
      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(builder: (_) => const MainScreen()),
        (route) => false,
      );
    } else {
      Navigator.pop(context, true);
    }
  }

  Future<void> _skipPage() async {
    final home = await UserStorage.getSelectedHome();

    if (home != null) {
      final homeId = home['id'] as String;

      try {
        await UserStorage.saveUsage(homeId, answers);
      } catch (_) {
        // Ignore save errors on skip — user is leaving.
      }

      final updatedHome = Map<String, dynamic>.from(home);
      updatedHome['behaviorCompleted'] = false;
      await UserStorage.updateHome(updatedHome);
    }

    if (!mounted) return;

    if (widget.fromRegistration) {
      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(builder: (_) => const MainScreen()),
        (route) => false,
      );
    } else {
      Navigator.pop(context, false);
    }
  }

  Widget _buildChoiceQuestion(Map<String, dynamic> question) {
    final String key = question['key'];
    final List<String> options = List<String>.from(question['options']);
    final String type = question['type'];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: List.generate(options.length, (i) {
        final option = options[i];
        final value = type == 'bool'
            ? (option == 'Yes')
            : type == 'numeric'
            ? List<int>.from(question['values'])[i]
            : option;

        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: OptionTile(
            text: option,
            selected: answers[key] == value,
            onTap: () => _selectAnswer(question, i),
          ),
        );
      }),
    );
  }

  Widget _buildHoursQuestion(Map<String, dynamic> question) {
    final String key = question['key'];
    final controller = key == 'home_occupancy_time'
        ? inBuildingHoursController
        : acHoursController;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Hours per day',
          style: TextStyle(
            fontSize: 14,
            color: ecowattText,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 10),
        TextField(
          controller: controller,
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly],
          onChanged: (_) => setState(() {}),
          decoration: InputDecoration(
            hintText: 'Enter hours from 0 to 24',
            suffixText: 'hours/day',
            filled: true,
            fillColor: const Color(0xFFF3F3F5),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(14),
              borderSide: BorderSide.none,
            ),
          ),
        ),
        if (controller.text.isNotEmpty &&
            (int.tryParse(controller.text) == null ||
                int.parse(controller.text) > 24))
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text(
              'Please enter a value between 0 and 24 hours.',
              style: TextStyle(color: Colors.red, fontSize: 12),
            ),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final progress = (currentQuestion + 1) / questions.length;

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      body: SafeArea(
        child: Column(
          children: [
            Container(
              width: double.infinity,
              color: Colors.white,
              padding: const EdgeInsets.fromLTRB(24, 20, 24, 18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      if (currentQuestion > 0)
                        IconButton(
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(),
                          onPressed: _goBack,
                          icon: const Icon(
                            Icons.arrow_back_ios_new,
                            size: 20,
                            color: ecowattDark,
                          ),
                        ),
                      if (currentQuestion > 0) const SizedBox(width: 12),
                      const Expanded(
                        child: Text(
                          'Behavior Information',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w700,
                            color: ecowattDark,
                          ),
                        ),
                      ),
                      TextButton(
                        onPressed: _skipPage,
                        child: const Text(
                          'Skip',
                          style: TextStyle(
                            color: ecowattGreen,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Let us understand your behavior better',
                    style: TextStyle(color: ecowattText, fontSize: 14),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(10),
                          child: LinearProgressIndicator(
                            value: progress,
                            minHeight: 7,
                            backgroundColor: ecowattLightGray,
                            valueColor: const AlwaysStoppedAnimation<Color>(
                              ecowattGreen,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Text(
                        '${currentQuestion + 1}/${questions.length}',
                        style: const TextStyle(
                          color: ecowattText,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            Expanded(
              child: PageView.builder(
                controller: _pageController,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: questions.length,
                onPageChanged: (index) {
                  setState(() {
                    currentQuestion = index;
                  });
                },
                itemBuilder: (context, index) {
                  final question = questions[index];
                  return SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(28, 42, 28, 24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          width: 46,
                          height: 46,
                          decoration: const BoxDecoration(
                            color: Color(0xFFEFFDF4),
                            shape: BoxShape.circle,
                          ),
                          alignment: Alignment.center,
                          child: Text(
                            '${index + 1}',
                            style: const TextStyle(
                              color: ecowattGreen,
                              fontSize: 18,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                        const SizedBox(height: 24),
                        Text(
                          question['question'],
                          style: const TextStyle(
                            fontSize: 22,
                            height: 1.35,
                            fontWeight: FontWeight.w700,
                            color: ecowattDark,
                          ),
                        ),
                        const SizedBox(height: 32),
                        if (question['type'] == 'hours')
                          _buildHoursQuestion(question)
                        else
                          _buildChoiceQuestion(question),
                      ],
                    ),
                  );
                },
              ),
            ),
            Container(
              color: Colors.white,
              padding: const EdgeInsets.fromLTRB(24, 14, 24, 20),
              child: Row(
                children: [
                  if (currentQuestion > 0)
                    Expanded(
                      child: OutlinedButton(
                        onPressed: _goBack,
                        style: OutlinedButton.styleFrom(
                          minimumSize: const Size(0, 50),
                          side: const BorderSide(color: ecowattGreen),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        child: const Text(
                          'Back',
                          style: TextStyle(
                            color: ecowattGreen,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  if (currentQuestion > 0) const SizedBox(width: 12),
                  Expanded(
                    child: ElevatedButton(
                      onPressed: _isCurrentAnswered() ? _goNext : null,
                      style: ElevatedButton.styleFrom(
                        minimumSize: const Size(0, 50),
                        backgroundColor: ecowattGreen,
                        foregroundColor: Colors.white,
                        disabledBackgroundColor: ecowattLightGray,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                      child: Text(
                        currentQuestion == questions.length - 1
                            ? 'Finish'
                            : 'Next',
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _pageController.dispose();
    inBuildingHoursController.dispose();
    acHoursController.dispose();
    super.dispose();
  }
}
