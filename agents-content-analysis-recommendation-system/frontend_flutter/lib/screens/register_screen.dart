import 'package:flutter/material.dart';

import '../state/auth_scope.dart';
import 'login_screen.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({
    super.key,
    this.destination = const LoginDestination('/dashboard'),
  });

  final LoginDestination destination;

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _usernameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _register() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _error = null);
    try {
      await AuthScope.of(context).register(
        username: _usernameController.text.trim(),
        email: _emailController.text.trim(),
        password: _passwordController.text.trim(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('สร้างบัญชีสำเร็จ กรุณาเข้าสู่ระบบ')));
      Navigator.pushReplacementNamed(context, '/login',
          arguments: widget.destination);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = AuthScope.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('สมัครสมาชิก')),
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
                    Icon(Icons.person_add_alt_outlined,
                        size: 40, color: Theme.of(context).colorScheme.primary),
                    const SizedBox(height: 12),
                    Text('สร้างบัญชี Content Creator',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: _usernameController,
                      autofillHints: const [AutofillHints.username],
                      textInputAction: TextInputAction.next,
                      decoration: const InputDecoration(
                        labelText: 'ชื่อผู้ใช้',
                        prefixIcon: Icon(Icons.person_outline),
                      ),
                      validator: (value) {
                        if ((value?.trim() ?? '').length < 3) {
                          return 'ชื่อผู้ใช้ต้องมีอย่างน้อย 3 ตัวอักษร';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 12),
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
                      autofillHints: const [AutofillHints.newPassword],
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
                      onFieldSubmitted: (_) =>
                          auth.loading ? null : _register(),
                    ),
                    const SizedBox(height: 16),
                    if (_error != null)
                      Text(_error!,
                          style: TextStyle(
                              color: Theme.of(context).colorScheme.error)),
                    const SizedBox(height: 8),
                    FilledButton(
                      onPressed: auth.loading ? null : _register,
                      child: auth.loading
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Text('สมัครสมาชิก'),
                    ),
                    TextButton(
                      onPressed: auth.loading
                          ? null
                          : () => Navigator.pushReplacementNamed(
                              context, '/login',
                              arguments: widget.destination),
                      child: const Text('กลับไปเข้าสู่ระบบ'),
                    ),
                    TextButton.icon(
                      onPressed: auth.loading
                          ? null
                          : () => Navigator.pushNamedAndRemoveUntil(
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
