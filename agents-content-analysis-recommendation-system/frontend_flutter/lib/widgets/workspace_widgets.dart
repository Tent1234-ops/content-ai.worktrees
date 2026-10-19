import 'package:flutter/material.dart';

class PageHeader extends StatelessWidget {
  const PageHeader(
      {super.key, required this.title, this.subtitle, this.action});
  final String title;
  final String? subtitle;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final heading =
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title, style: Theme.of(context).textTheme.headlineSmall),
      if (subtitle != null) ...[
        const SizedBox(height: 8),
        Text(subtitle!, style: Theme.of(context).textTheme.bodyMedium)
      ],
    ]);
    return Padding(
        padding: const EdgeInsets.only(bottom: 24),
        child: LayoutBuilder(builder: (context, constraints) {
          if (action == null) return heading;
          if (constraints.maxWidth < 680) {
            return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  heading,
                  const SizedBox(height: 16),
                  Align(alignment: Alignment.centerLeft, child: action)
                ]);
          }
          return Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
            Expanded(child: heading),
            const SizedBox(width: 24),
            Flexible(
                child: Align(alignment: Alignment.centerRight, child: action!))
          ]);
        }));
  }
}

class StatusBadge extends StatelessWidget {
  const StatusBadge(
      {super.key, required this.label, required this.icon, this.color});
  final String label;
  final IconData icon;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final tone = color ?? Theme.of(context).colorScheme.primary;
    return Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
            color: tone.withValues(alpha: 0.09),
            borderRadius: BorderRadius.circular(6)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 16, color: tone),
          const SizedBox(width: 6),
          Flexible(
              child: Text(label,
                  style: Theme.of(context)
                      .textTheme
                      .labelMedium
                      ?.copyWith(color: tone)))
        ]));
  }
}

class SectionHeading extends StatelessWidget {
  const SectionHeading({super.key, required this.title, required this.icon});
  final String title;
  final IconData icon;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(children: [
        Icon(icon, color: Theme.of(context).colorScheme.primary, size: 22),
        const SizedBox(width: 10),
        Expanded(
            child: Text(title, style: Theme.of(context).textTheme.titleMedium))
      ]));
}
