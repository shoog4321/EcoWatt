import 'dart:async';

import 'package:flutter/material.dart';
import '../widgets/ecowatt_widgets.dart';
import '../advice_api.dart';
import '../user_storage.dart';

class AdviceScreen extends StatefulWidget {
  const AdviceScreen({super.key});

  @override
  State<AdviceScreen> createState() => _AdviceScreenState();
}

class _AdviceScreenState extends State<AdviceScreen> {
  List<Map<String, dynamic>> advice = [];
  bool isLoading = true;

  // Latest advice-generation job: {bill_id, status, error, updated_at} or null.
  Map<String, dynamic>? job;
  Timer? _poller;

  @override
  void initState() {
    super.initState();
    loadAdvice();
  }

  @override
  void dispose() {
    _poller?.cancel();
    super.dispose();
  }

  Future<void> loadAdvice() async {
    if (mounted) setState(() => isLoading = true);

    final rows = await UserStorage.getAdvice(latestBillOnly: true);

    Map<String, dynamic>? latest;
    try {
      latest = await AdviceApi.latestJob();
    } catch (_) {
      // advice_jobs not available yet: just show whatever advice exists.
    }

    if (!mounted) return;

    setState(() {
      advice = rows;
      job = latest;
      isLoading = false;
    });
    _updatePolling();
  }

  bool get _jobActive =>
      job?['status'] == 'pending' || job?['status'] == 'running';

  // While the backend/GPU is working, check every 5 s and reload when it finishes.
  void _updatePolling() {
    if (_jobActive && _poller == null) {
      _poller = Timer.periodic(const Duration(seconds: 5), (_) => _pollJob());
    } else if (!_jobActive) {
      _poller?.cancel();
      _poller = null;
    }
  }

  Future<void> _pollJob() async {
    Map<String, dynamic>? latest;
    try {
      latest = await AdviceApi.latestJob();
    } catch (_) {
      return;
    }
    if (!mounted) return;

    final stillActive =
        latest?['status'] == 'pending' || latest?['status'] == 'running';
    if (!stillActive) {
      await loadAdvice(); // finished (or failed): fetch the advice rows
    } else {
      setState(() => job = latest);
    }
  }

  Future<void> _retry() async {
    final billId = job?['bill_id']?.toString();
    if (billId == null) return;
    try {
      await AdviceApi.regenerate(billId);
    } on AdviceApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.message)));
      return;
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Could not reach the server. Try again later.'),
        ),
      );
      return;
    }
    await loadAdvice();
  }

  Future<void> _toggleApplied(Map<String, dynamic> item) async {
    final id = item['id'] as String;
    final current = item['isApplied'] == true;

    setState(() {
      final idx = advice.indexWhere((a) => a['id'] == id);
      if (idx != -1) advice[idx] = {...advice[idx], 'isApplied': !current};
    });

    try {
      await UserStorage.setAdviceApplied(id, !current);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        final idx = advice.indexWhere((a) => a['id'] == id);
        if (idx != -1) advice[idx] = {...advice[idx], 'isApplied': current};
      });
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Failed to update: $e')));
    }
  }

  Widget _emptyAdviceState() {
    return Container(
      padding: const EdgeInsets.fromLTRB(28, 48, 28, 48),
      child: Column(
        children: [
          Container(
            width: 74,
            height: 74,
            decoration: const BoxDecoration(
              color: Color(0x1408A045),
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.lightbulb_outline,
              color: ecowattGreen,
              size: 36,
            ),
          ),
          const SizedBox(height: 20),
          const Text(
            'No advice yet',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          const Text(
            'Add a bill and complete your behavior information to receive personalized advice.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey, fontSize: 14, height: 1.5),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final appliedCount = advice.where((a) => a['isApplied'] == true).length;

    return Scaffold(
      backgroundColor: ecowattPageBg,
      body: ListView(
        padding: EdgeInsets.zero,
        children: [
          const EcowattPageHeader(
            title: 'Advice',
            subtitle: 'AI-powered advice for you',
          ),
          EcowattOverlap(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _GreatJobCard(appliedCount: appliedCount),
                const SizedBox(height: 20),
                _ProgressCard(appliedCount: appliedCount),

                const SizedBox(height: 24),

                const Text(
                  'Advice',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: ecowattDark,
                  ),
                ),

                const SizedBox(height: 6),

                const Row(
                  children: [
                    Icon(Icons.info_outline, size: 16, color: ecowattGray),
                    SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        'Click on any advice to mark it as applied',
                        style: TextStyle(fontSize: 12, color: ecowattGray),
                      ),
                    ),
                  ],
                ),

                const SizedBox(height: 12),

                if (job != null && job!['status'] != 'done') ...[
                  _StatusBanner(
                    status: job!['status'].toString(),
                    onRetry: _retry,
                  ),
                  const SizedBox(height: 12),
                ],

                if (isLoading)
                  const Padding(
                    padding: EdgeInsets.only(top: 60),
                    child: Center(
                      child: CircularProgressIndicator(color: ecowattGreen),
                    ),
                  )
                else if (advice.isEmpty)
                  _emptyAdviceState()
                else
                  for (final item in advice) ...[
                    _AdviceItem(
                      type: (item['category'] ?? 'general').toString(),
                      title: (item['title'] ?? '').toString(),
                      advice: (item['content'] ?? '').toString(),
                      applied: item['isApplied'] == true,
                      onTap: () => _toggleApplied(item),
                    ),
                    const SizedBox(height: 14),
                  ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Shows progress of advice generation (pending/running) or a retry on failure.
class _StatusBanner extends StatelessWidget {
  final String status;
  final VoidCallback onRetry;

  const _StatusBanner({required this.status, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    final failed = status == 'failed';

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: failed ? const Color(0xFFFFF4E5) : const Color(0xFFEFFDF4),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: failed ? const Color(0xFFFFC078) : const Color(0xFF86EFAC),
        ),
      ),
      child: Row(
        children: [
          if (failed)
            const Icon(Icons.error_outline, color: Color(0xFFE8590C))
          else
            const SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(
                strokeWidth: 2.5,
                color: ecowattGreen,
              ),
            ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              failed
                  ? 'We could not prepare advice for your latest bill.'
                  : 'Preparing your personalized advice. This can take a few minutes.',
              style: const TextStyle(
                color: ecowattDark,
                fontSize: 13,
                height: 1.4,
              ),
            ),
          ),
          if (failed)
            TextButton(onPressed: onRetry, child: const Text('Retry')),
        ],
      ),
    );
  }
}

class _GreatJobCard extends StatelessWidget {
  final int appliedCount;

  const _GreatJobCard({required this.appliedCount});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF06C755),
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.12),
            blurRadius: 10,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.25),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.auto_awesome, color: Colors.white),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Text(
              appliedCount == 0
                  ? 'Start applying advice to track your progress.'
                  : 'Great Job!\nYou’ve applied $appliedCount energy-saving advice.',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 14,
                height: 1.35,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProgressCard extends StatelessWidget {
  final int appliedCount;

  const _ProgressCard({required this.appliedCount});

  @override
  Widget build(BuildContext context) {
    return _WhiteCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.auto_awesome, color: ecowattGreen),
              SizedBox(width: 8),
              Text(
                'Your Progress',
                style: TextStyle(
                  color: ecowattDark,
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Container(
            height: 92,
            width: double.infinity,
            decoration: BoxDecoration(
              color: const Color(0xFFEFFDF4),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Center(
              child: Text(
                '$appliedCount\nAdvice Applied',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: ecowattGreen,
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                  height: 1.35,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _AdviceItem extends StatelessWidget {
  final String type;
  final String advice;
  final String title;
  final bool applied;
  final VoidCallback onTap;

  const _AdviceItem({
    required this.type,
    required this.advice,
    required this.title,
    required this.applied,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: applied ? const Color(0xFFEFFDF4) : Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: applied ? const Color(0xFF86EFAC) : ecowattLightGray,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.06),
              blurRadius: 8,
              offset: const Offset(0, 3),
            ),
          ],
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Checkbox(
              value: applied,
              activeColor: ecowattGreen,
              onChanged: (_) => onTap(),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: const Color(0xFFDCFCE7),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      type,
                      style: const TextStyle(
                        color: ecowattGreen,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    title,
                    style: const TextStyle(
                      color: ecowattDark,
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    advice,
                    style: const TextStyle(
                      color: ecowattText,
                      fontSize: 14,
                      height: 1.45,
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
}

class _WhiteCard extends StatelessWidget {
  final Widget child;

  const _WhiteCard({required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.08),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: child,
    );
  }
}
