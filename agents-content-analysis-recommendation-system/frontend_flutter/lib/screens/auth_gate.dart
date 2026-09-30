import 'package:flutter/material.dart';

import '../state/auth_scope.dart';

class AuthGate extends StatelessWidget {
  const AuthGate({super.key, this.destination = '/dashboard', this.arguments});

  final String destination;
  final Object? arguments;

  @override
  Widget build(BuildContext context) {
    final auth = AuthScope.of(context);
    if (!auth.initialized) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!context.mounted || ModalRoute.of(context)?.isCurrent != true) return;
      Navigator.pushReplacementNamed(
        context,
        destination,
        arguments: arguments,
      );
    });

    return const Scaffold(body: Center(child: CircularProgressIndicator()));
  }
}
