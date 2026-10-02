import 'package:flutter/material.dart';

import '../state/auth_scope.dart';

class LoginDestination {
  const LoginDestination(this.route, {this.arguments});

  final String route;
  final Object? arguments;
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    this.destination = const LoginDestination('/dashboard'),
  });

  final LoginDestination destination;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _error = null);
    try {
      await AuthScope.of(context).login(
        _emailController.text.trim(),
        _passwordController.text.trim(),
      );
      if (!mounted) return;
      Navigator.pushNamedAndRemoveUntil(
        context,
        widget.destination.route,
        (_) => false,
        arguments: widget.destination.arguments,
      );
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = AuthScope.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('เข้าสู่ระบบ')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: AutofillGroup(
              child: Form(
                key: _formKey,
                child: ListView(
                  shrinkWrap: true,
                  children: [
                    Icon(Icons.account_circle_outlined,
                        size: 40, color: Theme.of(context).colorScheme.primary),
                    const SizedBox(height: 12),
                    Text('เข้าสู่ระบบ Content AI',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(height: 4),
                    Text('เข้าสู่ระบบเพื่อวิเคราะห์คลิปและเปิดผลที่บันทึกไว้',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.bodyMedium),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: _emailController,
                      autofillHints: const [AutofillHints.email],
                      textInputAction: TextInputAction.next,
                      decoration: const InputDecoration(
                        labelText: 'อีเมล',
                        prefixIcon: Icon(Icons.email_outlined),
                      ),
                      keyboardType: TextInputType.emailAddress,
                      validator: (value) {
                        final text = value?.trim() ?? '';
                        if (!text.contains('@')) {
                          return 'กรุณากรอกอีเมลให้ถูกต้อง';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _passwordController,
                      autofillHints: const [AutofillHints.password],
                      textInputAction: TextInputAction.done,
                      enableSuggestions: false,
                      autocorrect: false,
                      decoration: const InputDecoration(
                        labelText: 'รหัสผ่าน',
                        prefixIcon: Icon(Icons.lock_outline),
                      ),
                      obscureText: true,
                      validator: (value) {
                        if ((value ?? '').length < 8) {
                          return 'รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร';
                        }
                        return null;
                      },
                      onFieldSubmitted: (_) => auth.loading ? null : _login(),
                    ),
                    const SizedBox(height: 16),
                    if (_error != null)
                      Text(_error!,
                          style: TextStyle(
                              color: Theme.of(context).colorScheme.error)),
                    const SizedBox(height: 8),
                    FilledButton(
                      onPressed: auth.loading ? null : _login,
                      child: auth.loading
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Text('เข้าสู่ระบบ'),
                    ),
                    TextButton(
                      onPressed: auth.loading
                          ? null
                          : () => Navigator.pushNamed(context, '/register',
                              arguments: widget.destination),
                      child: const Text('สร้างบัญชีใหม่'),
                    ),
                    TextButton.icon(
                      onPressed: () => Navigator.pushNamedAndRemoveUntil(
                          context, '/dashboard', (_) => false),
                      icon: const Icon(Icons.trending_up),
                      label: const Text('กลับไปดูเทรนด์'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
