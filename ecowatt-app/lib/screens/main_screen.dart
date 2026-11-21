import '../widgets/ecowatt_widgets.dart';
import 'package:flutter/material.dart';
import 'home_screen.dart';
import 'bills_screen.dart';
import 'advice_screen.dart';
import 'profile_screen.dart';
import '../user_storage.dart';

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  bool showProfileNotification = false;

  @override
  void initState() {
    super.initState();
    _checkBehaviorInformation();
  }

  Future<void> _checkBehaviorInformation() async {
    final home = await UserStorage.getSelectedHome();

    if (!mounted) return;

    setState(() {
      showProfileNotification =
          home != null && home['behaviorCompleted'] != true;
    });
  }

  int currentIndex = 0;

  final pages = const [
    HomeScreen(),
    BillsScreen(),
    AdviceScreen(),
    ProfileScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // Green strip pinned behind the status bar: when a tab scrolls, its cards
      // pass under it instead of under the clock.
      body: Stack(
        children: [
          pages[currentIndex],
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            height: MediaQuery.paddingOf(context).top,
            child: const ColoredBox(color: ecowattGreen),
          ),
        ],
      ),

      bottomNavigationBar: BottomNavigationBar(
        currentIndex: currentIndex,
        selectedItemColor: const Color(0xFF08A045),
        unselectedItemColor: const Color(0xFF9CA3AF),
        type: BottomNavigationBarType.fixed,

        onTap: (index) async {
          setState(() {
            currentIndex = index;
          });

          await _checkBehaviorInformation();
        },

        items: [
          const BottomNavigationBarItem(
            icon: Icon(Icons.home_outlined),
            activeIcon: Icon(Icons.home),
            label: 'Home',
          ),
          const BottomNavigationBarItem(
            icon: Icon(Icons.receipt_long_outlined),
            activeIcon: Icon(Icons.receipt_long),
            label: 'Bills',
          ),
          const BottomNavigationBarItem(
            icon: Icon(Icons.lightbulb_outline),
            label: 'Advice',
          ),
          BottomNavigationBarItem(
            icon: Stack(
              clipBehavior: Clip.none,
              children: [
                const Icon(Icons.person_outline),

                if (showProfileNotification)
                  Positioned(
                    right: -3,
                    top: -3,
                    child: Container(
                      width: 9,
                      height: 9,
                      decoration: const BoxDecoration(
                        color: Colors.red,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
              ],
            ),
            label: 'Profile',
          ),
        ],
      ),
    );
  }
}
