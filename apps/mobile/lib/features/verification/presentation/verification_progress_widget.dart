import 'package:flutter/material.dart';

import '../domain/verification.dart';

/// Shared "Verification Progress" widget — Module 3B. Mirrors
/// apps/web/src/components/VerificationProgress.tsx. Used by
/// VerificationDashboardScreen and embeddable elsewhere.
class VerificationProgressWidget extends StatelessWidget {
  const VerificationProgressWidget({super.key, required this.score});

  final VerificationScore score;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  VerificationScore.levelLabels[score.level] ?? score.level,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                Text('${score.percentage}%', style: Theme.of(context).textTheme.headlineSmall),
              ],
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: score.percentage / 100,
                minHeight: 8,
                backgroundColor: Colors.grey.shade200,
                valueColor: const AlwaysStoppedAnimation(Colors.green),
              ),
            ),
            if (score.nextLevel != null) ...[
              const SizedBox(height: 8),
              Text('Next level: ${VerificationScore.levelLabels[score.nextLevel] ?? score.nextLevel}'),
            ],
            if (score.missingRequirements.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text('Missing requirements', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 4),
              ...score.missingRequirements.map(
                (req) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text('• ${req.label} (+${req.weight}%)'),
                ),
              ),
            ],
            if (score.missingRequirements.isEmpty) ...[
              const SizedBox(height: 12),
              const Text('All requirements met — fully verified.', style: TextStyle(color: Colors.green)),
            ],
          ],
        ),
      ),
    );
  }
}
