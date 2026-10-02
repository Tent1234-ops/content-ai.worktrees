import 'package:flutter/material.dart';

ThemeData buildAppTheme(Brightness brightness) {
  final dark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: const Color(0xFF087FAD),
    brightness: brightness,
    primary: dark ? const Color(0xFF70C9EB) : const Color(0xFF006A92),
    secondary: dark ? const Color(0xFF83CEB1) : const Color(0xFF167357),
    tertiary: const Color(0xFF99620E),
    surface: dark ? const Color(0xFF202326) : Colors.white,
    onSurface: dark ? const Color(0xFFF1F3F4) : const Color(0xFF20262B),
    onSurfaceVariant: dark ? const Color(0xFFB7C1C7) : const Color(0xFF54616B),
    outlineVariant: dark ? const Color(0xFF424B51) : const Color(0xFFDDE4E8),
  );
  final base = ThemeData(useMaterial3: true, colorScheme: scheme);
  final border = OutlineInputBorder(
      borderRadius: BorderRadius.circular(8),
      borderSide: BorderSide(color: scheme.outlineVariant));
  final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(8));
  return base.copyWith(
    scaffoldBackgroundColor:
        dark ? const Color(0xFF171A1C) : const Color(0xFFF4F6F8),
    textTheme: base.textTheme
        .copyWith(
          displayLarge: base.textTheme.displayLarge?.copyWith(letterSpacing: 0),
          displayMedium:
              base.textTheme.displayMedium?.copyWith(letterSpacing: 0),
          displaySmall: base.textTheme.displaySmall?.copyWith(letterSpacing: 0),
          headlineLarge:
              base.textTheme.headlineLarge?.copyWith(letterSpacing: 0),
          headlineMedium:
              base.textTheme.headlineMedium?.copyWith(letterSpacing: 0),
          headlineSmall: const TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.w700,
              height: 1.4,
              letterSpacing: 0),
          titleLarge: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w600,
              height: 1.4,
              letterSpacing: 0),
          titleMedium: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              height: 1.5,
              letterSpacing: 0),
          titleSmall: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              height: 1.5,
              letterSpacing: 0),
          bodyLarge:
              const TextStyle(fontSize: 16, height: 1.6, letterSpacing: 0),
          bodyMedium:
              const TextStyle(fontSize: 14, height: 1.6, letterSpacing: 0),
          bodySmall: TextStyle(
              fontSize: 12,
              height: 1.5,
              letterSpacing: 0,
              color: scheme.onSurfaceVariant),
          labelLarge: const TextStyle(
              fontSize: 14, fontWeight: FontWeight.w600, letterSpacing: 0),
          labelMedium: const TextStyle(
              fontSize: 12, fontWeight: FontWeight.w600, letterSpacing: 0),
          labelSmall: const TextStyle(fontSize: 11, letterSpacing: 0),
        )
        .apply(bodyColor: scheme.onSurface, displayColor: scheme.onSurface),
    appBarTheme: AppBarTheme(
        backgroundColor: scheme.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        centerTitle: false,
        toolbarHeight: 64,
        titleTextStyle: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
            color: scheme.onSurface,
            letterSpacing: 0),
        shape: Border(bottom: BorderSide(color: scheme.outlineVariant))),
    cardTheme: CardThemeData(
        color: scheme.surface,
        elevation: 0,
        margin: const EdgeInsets.symmetric(vertical: 6),
        shape: shape.copyWith(side: BorderSide(color: scheme.outlineVariant))),
    inputDecorationTheme: InputDecorationTheme(
        border: border,
        enabledBorder: border,
        focusedBorder: border.copyWith(
            borderSide: BorderSide(color: scheme.primary, width: 2)),
        filled: true,
        fillColor: scheme.surface,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 14)),
    iconButtonTheme: IconButtonThemeData(
      style: ButtonStyle(
        minimumSize: const WidgetStatePropertyAll(Size(44, 44)),
        iconSize: const WidgetStatePropertyAll(22),
        foregroundColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.disabled)) {
            return scheme.onSurface.withValues(alpha: 0.38);
          }
          return scheme.onSurfaceVariant;
        }),
        overlayColor: WidgetStatePropertyAll(
          scheme.primary.withValues(alpha: 0.10),
        ),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
            shape: shape,
            minimumSize: const Size(44, 44),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14))),
    outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
            shape: shape,
            minimumSize: const Size(44, 44),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14))),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        shape: shape,
        minimumSize: const Size(44, 44),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      ),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
        style: ButtonStyle(shape: WidgetStatePropertyAll(shape))),
    chipTheme: ChipThemeData(
        shape: shape,
        side: BorderSide(color: scheme.outlineVariant),
        backgroundColor: scheme.surfaceContainerLow,
        labelStyle: TextStyle(fontSize: 12, color: scheme.onSurface)),
    dividerTheme:
        DividerThemeData(color: scheme.outlineVariant, thickness: 1, space: 24),
    dataTableTheme: DataTableThemeData(
        headingRowColor: WidgetStatePropertyAll(scheme.surfaceContainerLow),
        headingRowHeight: 48,
        dataRowMinHeight: 56,
        dataRowMaxHeight: 88,
        columnSpacing: 24,
        horizontalMargin: 16),
    dialogTheme: DialogThemeData(
        shape: shape,
        backgroundColor: scheme.surface,
        surfaceTintColor: Colors.transparent),
    snackBarTheme:
        SnackBarThemeData(behavior: SnackBarBehavior.floating, shape: shape),
    tooltipTheme: TooltipThemeData(
      waitDuration: const Duration(milliseconds: 450),
      showDuration: const Duration(seconds: 3),
      textStyle: TextStyle(
        color: scheme.onInverseSurface,
        fontSize: 12,
        letterSpacing: 0,
      ),
    ),
    listTileTheme: ListTileThemeData(
      minLeadingWidth: 24,
      iconColor: scheme.onSurfaceVariant,
      selectedColor: scheme.primary,
      selectedTileColor: scheme.primaryContainer.withValues(alpha: 0.55),
      shape: shape,
    ),
    tabBarTheme: TabBarThemeData(
        labelColor: scheme.primary,
        unselectedLabelColor: scheme.onSurfaceVariant,
        indicatorColor: scheme.primary,
        dividerColor: scheme.outlineVariant),
  );
}
