import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../widgets/trend_category_donut.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/dashboard_overview.dart';
import '../repositories/dashboard_repository.dart';
import '../state/auth_scope.dart';
import '../widgets/app_shell.dart';
import '../widgets/state_widgets.dart';
import '../widgets/trend_detail_panel.dart';
import '../widgets/trend_catalog.dart';
import '../widgets/dashboard_personal_dialog.dart';
import '../widgets/trend_history_panel.dart';
import 'login_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key, this.repository});

  final DashboardRepository? repository;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen>
    with SingleTickerProviderStateMixin {
  static const _platforms = ['youtube', 'google'];

  late final DashboardRepository _repository;
  late final TabController _platformTabController;
  DashboardOverview? _data;
  LiveTrendSnapshot? _snapshot;
  YouTubeCategoryTrendSnapshot? _youtubeCategorySnapshot;
  List<FollowedTopicItem> _followedTopics = const [];
  List<NotificationItem> _notifications = const [];
  Timer? _pollTimer;
  String? _error;
  Map<String, String> _sectionErrors = const {};
  String _selectedPlatform = 'youtube';
  String _categoryFilter = 'All';
  bool _loading = false;
  bool _loadingYoutubeCategory = false;
  bool _syncing = false;
  bool? _authenticated;
  int? _userId;
  int _loadGeneration = 0;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? DashboardRepository();
    _platformTabController = TabController(
      length: _platforms.length,
      vsync: this,
    );
    _pollTimer = Timer.periodic(const Duration(seconds: 60), (_) => _loadAll());
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final auth = AuthScope.of(context);
    if (_authenticated == auth.isAuthenticated &&
        _userId == auth.user?.userId) {
      return;
    }
    _authenticated = auth.isAuthenticated;
    _userId = auth.user?.userId;
    _loadGeneration++;
    _followedTopics = const [];
    _notifications = const [];
    _sectionErrors = const {};
    _data = _snapshot == null ? null : DashboardOverview.liveOnly(_snapshot!);
    _loading = false;
    _loadAll();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _platformTabController.dispose();
    super.dispose();
  }

  Future<void> _loadAll() async {
    if (_loading) return;
    final generation = _loadGeneration;
    final signedIn = _authenticated == true;
    setState(() {
      _loading = true;
      _error = null;
    });
    final overviewRequest = signedIn
        ? _capture(_repository.getOverview())
        : Future.value(const _DashboardLoadResult<DashboardOverview>._());
    final snapshotRequest = _capture(signedIn
        ? _repository.getLiveTrendSnapshot(limit: 50)
        : _repository.getPublicTrendSnapshot(limit: 50));
    final requestedCategoryId =
        _selectedPlatform == 'youtube' && _categoryFilter != 'All'
            ? _categoryFilter
            : null;
    final youtubeCategoriesRequest = _capture(
      _repository.getYouTubeCategoryTrendSnapshot(
        categoryId: requestedCategoryId,
        limit: 50,
      ),
    );
    final topicsRequest = signedIn
        ? _capture(_repository.getFollowedTopics())
        : Future.value(const _DashboardLoadResult<List<FollowedTopicItem>>._());
    final notificationsRequest = signedIn
        ? _capture(_repository.getNotifications(limit: 20))
        : Future.value(const _DashboardLoadResult<List<NotificationItem>>._());

    final overviewResult = await overviewRequest;
    final snapshotResult = await snapshotRequest;
    final youtubeCategoriesResult = await youtubeCategoriesRequest;
    final topicsResult = await topicsRequest;
    final notificationsResult = await notificationsRequest;
    if (!mounted || generation != _loadGeneration) return;

    final errors = <String, String>{};
    if (overviewResult.error != null) {
      errors['Overview'] = overviewResult.error.toString();
    }
    if (snapshotResult.error != null) {
      errors['Live trends'] = snapshotResult.error.toString();
    }
    if (youtubeCategoriesResult.error != null) {
      errors['YouTube categories'] = youtubeCategoriesResult.error.toString();
    }
    if (topicsResult.error != null) {
      errors['Followed topics'] = topicsResult.error.toString();
    }
    if (notificationsResult.error != null) {
      errors['Notifications'] = notificationsResult.error.toString();
    }

    final liveSnapshot = snapshotResult.value?.retainPreviousItems(_snapshot);
    setState(() {
      if (liveSnapshot != null) {
        _snapshot = liveSnapshot;
      }
      final categorySelectionUnchanged = requestedCategoryId == null
          ? !(_selectedPlatform == 'youtube' && _categoryFilter != 'All')
          : _selectedPlatform == 'youtube' &&
              _categoryFilter == requestedCategoryId;
      if (youtubeCategoriesResult.value != null && categorySelectionUnchanged) {
        _youtubeCategorySnapshot = youtubeCategoriesResult.value;
      }
      if (overviewResult.value != null) {
        _data = overviewResult.value;
      } else if (_data == null && liveSnapshot != null) {
        _data = DashboardOverview.liveOnly(liveSnapshot);
      }
      if (topicsResult.value != null) {
        _followedTopics = topicsResult.value!;
      }
      if (notificationsResult.value != null) {
        _notifications = notificationsResult.value!
            .where((n) => n.platform != 'tiktok')
            .toList();
      }
      _sectionErrors = errors;
      _error = _data == null
          ? errors['Overview'] ??
              errors['Live trends'] ??
              'ไม่สามารถโหลดหน้า Dashboard ได้'
          : null;
      _loading = false;
    });

    if (signedIn && liveSnapshot != null && liveSnapshot.newCount > 0) {
      await _loadNotificationsOnly();
      if (!mounted || generation != _loadGeneration) return;
    }

    if (signedIn &&
        liveSnapshot != null &&
        liveSnapshot.newNotifications.isNotEmpty) {
      final first = liveSnapshot.newNotifications.first;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            liveSnapshot.newCount == 1
                ? first.title
                : 'พบเทรนด์ใหม่ ${liveSnapshot.newCount} รายการ',
          ),
        ),
      );
    }
  }

  Future<_DashboardLoadResult<T>> _capture<T>(Future<T> request) async {
    try {
      return _DashboardLoadResult<T>.success(await request);
    } catch (error) {
      return _DashboardLoadResult<T>.failure(error);
    }
  }

  Future<void> _syncTrends() async {
    setState(() => _syncing = true);
    try {
      final results = await _repository.syncAllTrendsLive(limit: 50);
      final fetched =
          results.fold<int>(0, (sum, item) => sum + item.totalFetched);
      final saved = results.fold<int>(
        0,
        (sum, item) => sum + item.created + item.updated,
      );
      final notifications = results.fold<int>(
        0,
        (sum, item) => sum + item.notifications,
      );
      final failed = results.where((item) => item.failed).length;
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            failed == 0
                ? 'อัปเดตสำเร็จ: ดึง $fetched รายการ บันทึก $saved รายการ และแจ้งเตือน $notifications รายการ'
                : 'อัปเดตเสร็จโดยมี $failed แหล่งข้อมูลผิดพลาด: ดึง $fetched รายการ และบันทึก $saved รายการ',
          ),
        ),
      );
      await _loadAll();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('อัปเดตข้อมูลเทรนด์ไม่สำเร็จ: $error')),
      );
    } finally {
      if (mounted) {
        setState(() => _syncing = false);
      }
    }
  }

  Future<void> _toggleFollowTopic(DashboardTrendItem item) async {
    if (_authenticated != true) {
      Navigator.pushNamed(context, '/login',
          arguments: const LoginDestination('/dashboard'));
      return;
    }
    final value = item.title.trim().toLowerCase();
    final existing = _followedTopics.where(
      (topic) => topic.matchType == 'keyword' && topic.value == value,
    );
    try {
      if (existing.isNotEmpty) {
        await _repository.unfollowTopic(existing.first.id);
      } else {
        await _repository.followTopic(item.title);
      }
      await _loadFollowStateOnly();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('ติดตามหัวข้อไม่สำเร็จ: $error')),
      );
    }
  }

  Future<void> _showTrendDetails(DashboardTrendItem item) {
    return showTrendDetailPanel(
      context: context,
      item: item,
    );
  }

  Future<void> _openTrendSource(DashboardTrendItem item) async {
    final uri = Uri.tryParse(item.videoUrl);
    if (uri == null || !uri.hasScheme) return;
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('ไม่สามารถเปิดลิงก์ต้นทางได้')),
      );
    }
  }

  Future<void> _loadFollowStateOnly() async {
    if (_authenticated != true) return;
    final generation = _loadGeneration;
    final topics = await _repository.getFollowedTopics();
    if (!mounted || generation != _loadGeneration) return;
    setState(() => _followedTopics = topics);
  }

  Future<void> _loadNotificationsOnly() async {
    if (_authenticated != true) return;
    final generation = _loadGeneration;
    try {
      final notifications = await _repository.getNotifications(limit: 20);
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        _notifications =
            notifications.where((n) => n.platform != 'tiktok').toList();
        if (_sectionErrors.containsKey('Notifications')) {
          final errors = Map<String, String>.from(_sectionErrors)
            ..remove('Notifications');
          _sectionErrors = errors;
        }
      });
    } catch (error) {
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        _sectionErrors = {
          ..._sectionErrors,
          'Notifications': error.toString(),
        };
      });
    }
  }

  Future<void> _openPersonalDialog({required bool following}) async {
    final auth = AuthScope.of(context);
    final ownerId = auth.user?.userId;
    if (!auth.isAuthenticated || ownerId == null) return;
    await showDialog<void>(
      context: context,
      builder: (_) => AuthScope(
          controller: auth,
          child: DashboardPersonalDialog(
              repository: _repository, following: following, ownerId: ownerId)),
    );
    if (!mounted || AuthScope.of(context).user?.userId != ownerId) return;
    await _loadAll();
  }

  Future<void> _logout() async {
    await AuthScope.of(context).logout();
    if (!mounted) return;
    Navigator.pushNamedAndRemoveUntil(context, '/dashboard', (_) => false);
  }

  bool _isFollowing(DashboardTrendItem item) {
    final value = item.title.trim().toLowerCase();
    return _followedTopics.any(
      (topic) => topic.matchType == 'keyword' && topic.value == value,
    );
  }

  void _changePlatform(String value) {
    setState(() {
      _selectedPlatform = value;
      _categoryFilter = 'All';
      _loadingYoutubeCategory = false;
    });
  }

  Future<void> _changeCategory(String value) async {
    setState(() {
      _categoryFilter = value;
      _loadingYoutubeCategory =
          _selectedPlatform == 'youtube' && value != 'All';
    });
    if (_selectedPlatform != 'youtube' || value == 'All') return;

    try {
      final snapshot = await _repository.getYouTubeCategoryTrendSnapshot(
        categoryId: value,
        limit: 50,
      );
      if (!mounted ||
          _selectedPlatform != 'youtube' ||
          _categoryFilter != value) {
        return;
      }
      setState(() {
        _youtubeCategorySnapshot = snapshot;
        _loadingYoutubeCategory = false;
        if (_sectionErrors.containsKey('YouTube categories')) {
          final errors = Map<String, String>.from(_sectionErrors)
            ..remove('YouTube categories');
          _sectionErrors = errors;
        }
      });
    } catch (error) {
      if (!mounted || _categoryFilter != value) return;
      setState(() {
        _loadingYoutubeCategory = false;
        _sectionErrors = {
          ..._sectionErrors,
          'YouTube categories': error.toString(),
        };
      });
    }
  }

  List<DashboardPlatformTrends> _displayPlatforms(DashboardOverview data) {
    final snapshot = _snapshot;
    if (snapshot == null) return data.platformTrends;
    final hasSnapshotItems =
        snapshot.platformTrends.any((platform) => platform.items.isNotEmpty);
    return hasSnapshotItems ? snapshot.platformTrends : data.platformTrends;
  }

  List<DashboardTrendItem> _allTrends(DashboardOverview data) {
    return _displayPlatforms(data)
        .expand((platform) => platform.items)
        .toList();
  }

  YouTubeTrendCategory? get _selectedYoutubeCategory {
    if (_selectedPlatform != 'youtube' || _categoryFilter == 'All') {
      return null;
    }
    final selected = _youtubeCategorySnapshot?.selectedCategory;
    if (selected?.categoryId == _categoryFilter) return selected;
    return null;
  }

  String? get _selectedYoutubeCategoryLabel {
    if (_selectedPlatform != 'youtube' || _categoryFilter == 'All') {
      return null;
    }
    final selected = _selectedYoutubeCategory;
    if (selected != null) {
      return _formatTrendCategory('youtube', selected.title);
    }
    for (final item in _youtubeCategorySnapshot?.categories ?? const []) {
      if (item.categoryId == _categoryFilter) {
        return _formatTrendCategory('youtube', item.title);
      }
    }
    return null;
  }

  List<DashboardTrendItem> _filteredTrends(DashboardOverview data) {
    final sourceItems =
        _selectedPlatform == 'youtube' && _categoryFilter != 'All'
            ? _selectedYoutubeCategory?.items ?? const <DashboardTrendItem>[]
            : _allTrends(data);
    return sourceItems.where((item) {
      final platformOk =
          _platformFamily(item.sourcePlatform) == _selectedPlatform;
      final category = _formatTrendCategory(
        item.sourcePlatform,
        item.category,
      );
      final categoryOk = _selectedPlatform == 'youtube'
          ? _categoryFilter == 'All' || item.categoryId == _categoryFilter
          : _categoryFilter == 'All' || category == _categoryFilter;
      return platformOk && categoryOk;
    }).toList()
      ..sort((a, b) {
        final leftRank = a.rank > 0 ? a.rank : 1 << 30;
        final rightRank = b.rank > 0 ? b.rank : 1 << 30;
        final rankComparison = leftRank.compareTo(rightRank);
        if (rankComparison != 0) return rankComparison;
        return a.title.toLowerCase().compareTo(b.title.toLowerCase());
      });
  }

  List<_CategoryOption> _categories(DashboardOverview data) {
    if (_selectedPlatform == 'youtube') {
      final categories = _youtubeCategorySnapshot?.categories ?? const [];
      return [
        const _CategoryOption(value: 'All', label: 'ทั้งหมด'),
        ...categories.map((item) {
          final title = _formatTrendCategory('youtube', item.title);
          final hasResult =
              item.providerStatus == 'ok' || item.providerStatus == 'empty';
          return _CategoryOption(
            value: item.categoryId,
            label: hasResult ? '$title (${item.total})' : title,
          );
        }),
      ];
    }
    final values = _allTrends(data)
        .where(
          (item) => _platformFamily(item.sourcePlatform) == _selectedPlatform,
        )
        .map(
          (item) => _formatTrendCategory(
            item.sourcePlatform,
            item.category,
          ),
        )
        .where((category) => category != 'All')
        .toSet()
        .toList()
      ..sort();
    return [
      const _CategoryOption(value: 'All', label: 'ทั้งหมด'),
      ...values.map((value) => _CategoryOption(value: value, label: value)),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final auth = AuthScope.of(context);
    final data = _data;
    final selectedPlatforms = data == null
        ? const <DashboardPlatformTrends>[]
        : _displayPlatforms(data)
            .where((item) => item.platform == _selectedPlatform)
            .toList();
    final selectedMode =
        selectedPlatforms.isEmpty ? '' : selectedPlatforms.first.mode;
    final unreadNotifications =
        _notifications.where((item) => !item.isRead).length;

    return AppShell(
      title: 'Content AI',
      currentRoute: '/dashboard',
      isAdmin: auth.isAdmin,
      onLogout: auth.isAuthenticated ? _logout : null,
      actions: [
        if (auth.isAuthenticated)
          Badge(
            isLabelVisible: unreadNotifications > 0,
            label: Text(
              unreadNotifications > 99 ? '99+' : '$unreadNotifications',
            ),
            child: IconButton(
              onPressed: () => _openPersonalDialog(following: false),
              icon: const Icon(Icons.notifications_outlined),
              tooltip: 'การแจ้งเตือนเทรนด์',
            ),
          ),
        if (auth.isAuthenticated)
          IconButton(
            onPressed: () => _openPersonalDialog(following: true),
            icon: const Icon(Icons.bookmarks_outlined),
            tooltip: 'หัวข้อที่ติดตาม',
          ),
        if (auth.isAdmin)
          IconButton(
            onPressed: _syncing ? null : _syncTrends,
            icon: _syncing
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.cloud_sync_outlined),
            tooltip: 'ดึงข้อมูลเทรนด์รอบใหม่',
          ),
        IconButton(
          onPressed: _loadAll,
          icon: const Icon(Icons.refresh),
          tooltip: 'รีเฟรช',
        ),
        if (!auth.isAuthenticated)
          TextButton.icon(
            onPressed: () => Navigator.pushNamed(context, '/login'),
            icon: const Icon(Icons.login),
            label: const Text('เข้าสู่ระบบ'),
          ),
      ],
      child: _error != null
          ? ErrorStateView(message: _error!, onRetry: _loadAll)
          : data == null
              ? const Center(child: CircularProgressIndicator())
              : RefreshIndicator(
                  onRefresh: _loadAll,
                  child: Center(
                      child: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 1440),
                          child: ListView(
                            padding: const EdgeInsets.all(16),
                            children: [
                              if (_loading) const LinearProgressIndicator(),
                              if (_sectionErrors.isNotEmpty) ...[
                                _DashboardWarning(errors: _sectionErrors),
                                const SizedBox(height: 16),
                              ],
                              _DashboardIntro(
                                totalTrends: _allTrends(data).length,
                                generatedAt: _snapshot?.generatedAt ?? '',
                                activePlatforms: _displayPlatforms(data)
                                    .where(
                                        (platform) => platform.items.isNotEmpty)
                                    .map((platform) => platform.platform)
                                    .toList(),
                              ),
                              const SizedBox(height: 16),
                              _TrendFilters(
                                platformTabController: _platformTabController,
                                category: _categoryFilter,
                                categories: _categories(data),
                                showCategories: _selectedPlatform == 'youtube',
                                onPlatformChanged: _changePlatform,
                                onCategoryChanged: (value) {
                                  _changeCategory(value);
                                },
                              ),
                              const SizedBox(height: 16),
                              if (_categoryFilter == 'All' &&
                                  (selectedMode == 'live_error' ||
                                      selectedMode == 'live_stale'))
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 16),
                                  child: Text(selectedMode == 'live_stale'
                                      ? 'การอัปเดตรอบล่าสุดไม่สำเร็จ กำลังแสดงข้อมูลที่เก็บไว้ล่าสุด'
                                      : 'ยังโหลดข้อมูลจาก ${_formatPlatformName(_selectedPlatform)} ไม่สำเร็จ กรุณาลองรีเฟรชภายหลัง'),
                                ),
                              _TrendDashboardSections(
                                platform: _selectedPlatform,
                                categoryLabel: _selectedYoutubeCategoryLabel,
                                generatedAt: _selectedPlatform == 'youtube' &&
                                        _categoryFilter != 'All'
                                    ? _youtubeCategorySnapshot?.generatedAt ??
                                        ''
                                    : _snapshot?.generatedAt ?? '',
                                trends: _filteredTrends(data),
                                isLoading: _loadingYoutubeCategory,
                                isFollowing: _isFollowing,
                                onToggleFollow: _toggleFollowTopic,
                                onOpenDetails: _showTrendDetails,
                                onOpenSource: _openTrendSource,
                              ),
                              const SizedBox(height: 16),
                              ...[
                                TrendHistoryPanel(
                                  repository: _repository,
                                  platform: _selectedPlatform,
                                  categoryId: _selectedPlatform == 'youtube' &&
                                          _categoryFilter != 'All'
                                      ? _categoryFilter
                                      : null,
                                  categoryLabel: _selectedYoutubeCategoryLabel,
                                  categoryName: (c) =>
                                      _formatTrendCategory('youtube', c),
                                  revision:
                                      '${_snapshot?.generatedAt}:${_youtubeCategorySnapshot?.generatedAt}',
                                ),
                                const SizedBox(height: 16),
                              ],
                              if (auth.isAdmin) ...[
                                _MetricsGrid(metrics: data.metrics),
                                const SizedBox(height: 16),
                              ],
                            ],
                          ))),
                ),
    );
  }
}

class _DashboardLoadResult<T> {
  const _DashboardLoadResult._({this.value, this.error});

  factory _DashboardLoadResult.success(T value) {
    return _DashboardLoadResult._(value: value);
  }

  factory _DashboardLoadResult.failure(Object error) {
    return _DashboardLoadResult._(error: error);
  }

  final T? value;
  final Object? error;
}

class _DashboardWarning extends StatelessWidget {
  const _DashboardWarning({required this.errors});

  final Map<String, String> errors;

  @override
  Widget build(BuildContext context) {
    final message = errors.entries
        .map((entry) => '${entry.key}: ${entry.value}')
        .join('\n');
    return Material(
      color: Theme.of(context).colorScheme.errorContainer,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              Icons.warning_amber_outlined,
              color: Theme.of(context).colorScheme.onErrorContainer,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'ข้อมูลบางส่วนอัปเดตไม่สำเร็จ ระบบจึงยังแสดงข้อมูลรอบก่อนหน้า\n$message',
                style: TextStyle(
                  color: Theme.of(context).colorScheme.onErrorContainer,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DashboardIntro extends StatelessWidget {
  const _DashboardIntro({
    required this.totalTrends,
    required this.generatedAt,
    required this.activePlatforms,
  });

  final int totalTrends;
  final String generatedAt;
  final List<String> activePlatforms;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: Row(
        children: [
          const Icon(Icons.trending_up),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Content AI',
                    style: Theme.of(context).textTheme.headlineMedium),
                Text('เทรนด์วิดีโอและคำค้นในประเทศไทย',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                FilledButton.icon(
                  onPressed: () => Navigator.pushNamed(context, '/upload'),
                  icon: const Icon(Icons.upload_file_outlined),
                  label: const Text('วิเคราะห์คลิปของฉัน'),
                ),
                const SizedBox(height: 4),
                Text(
                  activePlatforms.isEmpty
                      ? 'ยังไม่มีข้อมูลเทรนด์ในขณะนี้'
                      : '$totalTrends รายการจาก ${_formatPlatformList(activePlatforms)}',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                if (generatedAt.isNotEmpty)
                  Text(
                    'ตรวจล่าสุด ${_formatDateTime(generatedAt)}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TrendFilters extends StatelessWidget {
  const _TrendFilters({
    required this.platformTabController,
    required this.category,
    required this.categories,
    required this.showCategories,
    required this.onPlatformChanged,
    required this.onCategoryChanged,
  });

  final TabController platformTabController;
  final String category;
  final List<_CategoryOption> categories;
  final bool showCategories;
  final ValueChanged<String> onPlatformChanged;
  final ValueChanged<String> onCategoryChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final stacked = constraints.maxWidth < 760;
          final controlsWidth = stacked
              ? constraints.maxWidth
              : math.min(560.0, constraints.maxWidth);
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'เลือกแพลตฟอร์ม',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: controlsWidth,
                child: TabBar(
                  controller: platformTabController,
                  onTap: (index) {
                    const platforms = ['youtube', 'google'];
                    onPlatformChanged(platforms[index]);
                  },
                  tabs: const [
                    Tab(icon: Icon(Icons.play_circle_outline), text: 'YouTube'),
                    Tab(icon: Icon(Icons.search), text: 'Google'),
                  ],
                ),
              ),
              if (showCategories) ...[
                const SizedBox(height: 16),
                _FilterDropdown(
                  width: controlsWidth,
                  label: 'หมวดหมู่',
                  value: category,
                  values: categories,
                  onChanged: onCategoryChanged,
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _FilterDropdown extends StatelessWidget {
  const _FilterDropdown({
    required this.width,
    required this.label,
    required this.value,
    required this.values,
    required this.onChanged,
  });

  final double width;
  final String label;
  final String value;
  final List<_CategoryOption> values;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final safeValue = values.any((item) => item.value == value) ? value : 'All';
    return SizedBox(
      width: width,
      child: DropdownButtonFormField<String>(
        initialValue: safeValue,
        isExpanded: true,
        menuMaxHeight: 360,
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
        ),
        items: values
            .map(
              (item) => DropdownMenuItem(
                value: item.value,
                child: Text(
                  item.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            )
            .toList(),
        onChanged: (value) {
          if (value != null) onChanged(value);
        },
      ),
    );
  }
}

class _CategoryOption {
  const _CategoryOption({required this.value, required this.label});

  final String value;
  final String label;
}

class _TrendDashboardSections extends StatelessWidget {
  const _TrendDashboardSections({
    required this.platform,
    required this.categoryLabel,
    required this.generatedAt,
    required this.trends,
    required this.isLoading,
    required this.isFollowing,
    required this.onToggleFollow,
    required this.onOpenDetails,
    required this.onOpenSource,
  });

  final String platform;
  final String? categoryLabel;
  final String generatedAt;
  final List<DashboardTrendItem> trends;
  final bool isLoading;
  final bool Function(DashboardTrendItem item) isFollowing;
  final Future<void> Function(DashboardTrendItem item) onToggleFollow;
  final Future<void> Function(DashboardTrendItem item) onOpenDetails;
  final Future<void> Function(DashboardTrendItem item) onOpenSource;

  @override
  Widget build(BuildContext context) {
    if (isLoading) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Column(
            children: [
              LinearProgressIndicator(),
              SizedBox(height: 12),
              Text('กำลังโหลดอันดับของหมวดหมู่จากฐานข้อมูล'),
            ],
          ),
        ),
      );
    }
    final trendingNow = trends.take(50).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TrendCatalog(
          key: ValueKey('$platform:${categoryLabel ?? 'all'}'),
          platform: platform,
          title: _topTrendsTitle(platform, categoryLabel),
          subtitle: _topTrendsSubtitle(
            platform,
            categoryLabel,
            trendingNow.length,
          ),
          trends: trendingNow,
          emptyMessage: _noTrendsMessage(platform),
          isFollowing: isFollowing,
          onToggleFollow: onToggleFollow,
          onOpenDetails: onOpenDetails,
          onOpenSource: onOpenSource,
        ),
        if (categoryLabel == null &&
            _platformFamily(platform) == 'youtube') ...[
          const SizedBox(height: 16),
          TrendCategoryDonut(
            trends: trendingNow,
            categoryName: (item) =>
                _formatTrendCategory(item.sourcePlatform, item.category),
          ),
        ],
      ],
    );
  }
}

class _MetricsGrid extends StatelessWidget {
  const _MetricsGrid({required this.metrics});

  final DashboardMetrics metrics;

  @override
  Widget build(BuildContext context) {
    final items = [
      _MetricItem('ข้อมูลสำหรับฝึกและอ้างอิง', metrics.totalDatasetContents,
          Icons.dataset_outlined),
      _MetricItem('ผู้ใช้', metrics.totalUsers, Icons.people_outline),
      _MetricItem('คลิปที่ฉันวิเคราะห์', metrics.myAnalysisResults,
          Icons.assessment_outlined),
    ];

    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 720;
        return GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: items.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: wide ? 3 : 2,
            mainAxisExtent: 104,
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
          ),
          itemBuilder: (context, index) => _MetricCard(item: items[index]),
        );
      },
    );
  }
}

class _MetricItem {
  const _MetricItem(this.label, this.value, this.icon);

  final String label;
  final int value;
  final IconData icon;
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.item});

  final _MetricItem item;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(item.icon, color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.value.toString(),
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  Text(
                    item.label,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall,
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

String _formatPlatformName(String platform) {
  final normalized = platform.replaceAll('_', ' ').trim();
  if (normalized.isEmpty) return '-';
  return normalized.split(' ').map((part) {
    switch (part.toLowerCase()) {
      case 'youtube':
        return 'YouTube';
      case 'tiktok':
        return 'TikTok';
      default:
        return part.isEmpty
            ? part
            : '${part[0].toUpperCase()}${part.substring(1)}';
    }
  }).join(' ');
}

String _platformFamily(String platform) {
  final normalized = platform.toLowerCase();
  if (normalized.contains('youtube')) return 'youtube';
  if (normalized.contains('google')) return 'google';
  if (normalized.contains('tiktok')) return 'tiktok';
  return normalized;
}

String _topTrendsTitle(String platform, String? categoryLabel) {
  switch (_platformFamily(platform)) {
    case 'google':
      return 'อันดับคำค้นบน Google ตอนนี้';
    case 'tiktok':
      return 'อันดับวิดีโอบน TikTok ตอนนี้';
    default:
      if (categoryLabel != null) {
        return 'อันดับวิดีโอ YouTube หมวด$categoryLabel';
      }
      return 'อันดับวิดีโอบน YouTube ตอนนี้';
  }
}

String _topTrendsSubtitle(
  String platform,
  String? categoryLabel,
  int itemCount,
) {
  if (_platformFamily(platform) == 'google') {
    return 'เรียงตามลำดับคำค้นจาก Google ในข้อมูลรอบล่าสุด โดยไม่เทียบกับแพลตฟอร์มอื่น';
  }
  if (_platformFamily(platform) == 'youtube' && categoryLabel != null) {
    return 'YouTube ส่งกลับ $itemCount รายการในรอบล่าสุดของหมวด$categoryLabel (สูงสุด 50)';
  }
  final name = _formatPlatformName(platform);
  return 'เรียงตามลำดับวิดีโอจาก $name ในข้อมูลรอบล่าสุด โดยไม่เทียบกับแพลตฟอร์มอื่น';
}

String _noTrendsMessage(String platform) {
  final name = _formatPlatformName(platform);
  return 'ยังไม่มีข้อมูลเทรนด์ของ $name ที่ตรงกับตัวกรอง';
}

String _formatPlatformList(List<String> platforms) {
  final names = platforms.map(_formatPlatformName).toList();
  if (names.isEmpty) return '';
  if (names.length == 1) return names.first;
  if (names.length == 2) return '${names.first} และ ${names.last}';
  return '${names.sublist(0, names.length - 1).join(', ')} และ ${names.last}';
}

String _formatTrendCategory(String platform, String category) {
  final value = category.trim();
  final normalized = value.toLowerCase();
  final isGoogle = platform.toLowerCase().contains('google');
  final looksLikeRegion = value.length == 2 &&
      value.codeUnits.every(
        (character) =>
            (character >= 65 && character <= 90) ||
            (character >= 97 && character <= 122),
      );
  if (isGoogle &&
      (value.isEmpty ||
          looksLikeRegion ||
          {'general', 'search', 'thailand'}.contains(normalized))) {
    return 'คำค้นทั่วไป';
  }
  if (value.isEmpty || normalized == 'general') return 'ทั่วไป';
  return switch (normalized) {
    'music' => 'เพลงและดนตรี',
    'gaming' => 'เกม',
    'entertainment' => 'บันเทิง',
    'people & blogs' => 'บุคคลและบล็อก',
    'film & animation' => 'ภาพยนตร์และแอนิเมชัน',
    'autos & vehicles' => 'รถยนต์และยานพาหนะ',
    'pets & animals' => 'สัตว์เลี้ยงและสัตว์',
    'sports' => 'กีฬา',
    'news & politics' => 'ข่าวและการเมือง',
    'science & technology' => 'วิทยาศาสตร์และเทคโนโลยี',
    'education' => 'การศึกษา',
    _ => value,
  };
}

String _formatDateTime(String value) {
  final trimmed = value.trim();
  if (trimmed.isEmpty) return value;
  final hasTimezone = RegExp(
    r'(z|[+-]\d{2}:?\d{2})$',
    caseSensitive: false,
  ).hasMatch(trimmed);
  final parsed = DateTime.tryParse(hasTimezone ? trimmed : '${trimmed}Z');
  if (parsed == null) return value;
  final local = parsed.toLocal();
  final hour = local.hour.toString().padLeft(2, '0');
  final minute = local.minute.toString().padLeft(2, '0');
  return '${local.day}/${local.month} $hour:$minute';
}
