import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/common_models.dart';
import '../models/actionable_recommendations.dart';
import '../models/recommendation_result.dart';
import '../repositories/content_repository.dart';
import '../state/auth_scope.dart';
import '../widgets/app_shell.dart';
import '../widgets/analysis_settings_audit.dart';
import '../widgets/revision_comparison_panel.dart';
import '../widgets/current_trend_ideas_panel.dart';
import '../widgets/recommendation_evidence_panel.dart';
import '../widgets/actionable_advice_panel.dart';
import '../widgets/clip_revision_planner.dart';
import '../widgets/state_widgets.dart';

class ResultScreenArgs {
  const ResultScreenArgs({this.initialData, this.contentId});
  final AnalysisResultViewData? initialData;
  final int? contentId;
}

class ResultScreen extends StatefulWidget {
  const ResultScreen({super.key, this.repository});
  final ContentRepository? repository;
  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  late final ContentRepository _repository =
      widget.repository ?? ContentRepository();
  AnalysisResultViewData? _data;
  String? _error;
  int? _contentId;
  bool _initialized = false;
  bool _loading = false;
  bool _planDirty = false;
  int _viewVersion = 0;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_initialized) return;
    _initialized = true;
    final args =
        ModalRoute.of(context)?.settings.arguments as ResultScreenArgs?;
    _data = args?.initialData;
    _contentId = args?.contentId ?? _data?.contentId;
    if (_contentId != null) _loadContent();
  }

  Future<bool> _confirmLeaving() async {
    if (!_planDirty) return true;
    return await showDialog<bool>(
            context: context,
            builder: (context) => AlertDialog(
                    title: const Text('แผนปรับคลิปยังไม่บันทึก'),
                    content: const Text(
                        'ต้องการออกหรือโหลดข้อมูลใหม่โดยไม่บันทึกการเปลี่ยนแปลงหรือไม่?'),
                    actions: [
                      TextButton(
                          onPressed: () => Navigator.pop(context, false),
                          child: const Text('แก้ต่อ')),
                      TextButton(
                          onPressed: () => Navigator.pop(context, true),
                          child: const Text('ดำเนินการโดยไม่บันทึก'))
                    ])) ??
        false;
  }

  Future<void> _openRoute(String route) async {
    if (await _confirmLeaving() && mounted) Navigator.pushNamed(context, route);
  }

  Future<void> _loadContent() async {
    if (_contentId == null || _loading) return;
    if (!await _confirmLeaving() || !mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final response = await _repository.getContentResult(_contentId!);
      if (mounted) {
        setState(() {
          _data = response;
          _planDirty = false;
          _viewVersion++;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'โหลดผลวิเคราะห์ไม่สำเร็จ กรุณาลองอีกครั้ง');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    return PopScope(
        canPop: !_planDirty,
        onPopInvokedWithResult: (didPop, result) async {
          if (!didPop && await _confirmLeaving() && mounted) {
            setState(() => _planDirty = false);
            await Future<void>.delayed(Duration.zero);
            if (context.mounted) Navigator.pop(context, result);
          }
        },
        child: AppShell(
          title: 'ผลวิเคราะห์คลิป',
          isAdmin: AuthScope.of(context).isAdmin,
          actions: [
            if (_contentId != null)
              IconButton(
                  onPressed: _loading ? null : _loadContent,
                  icon: const Icon(Icons.refresh),
                  tooltip: 'โหลดผลวิเคราะห์ใหม่'),
          ],
          child: _loading && data == null
              ? const Center(child: CircularProgressIndicator())
              : _error != null
                  ? ErrorStateView(message: _error!, onRetry: _loadContent)
                  : data == null
                      ? const EmptyStateView(
                          title: 'ยังไม่มีผลวิเคราะห์',
                          message: 'ไม่พบรายการผลวิเคราะห์นี้',
                          icon: Icons.analytics_outlined)
                      : RefreshIndicator(
                          onRefresh: _loadContent,
                          child: ListView(
                              padding: const EdgeInsets.all(24),
                              children: [
                                if (_loading) const LinearProgressIndicator(),
                                Text(data.title,
                                    style: Theme.of(context)
                                        .textTheme
                                        .headlineSmall),
                                const SizedBox(height: 8),
                                Text(
                                    data.saved && data.contentId != null
                                        ? 'ผลวิเคราะห์บันทึกแล้ว · #${data.contentId}'
                                        : 'ผลนี้ยังไม่มีรายการที่ยืนยันว่าบันทึกแล้ว',
                                    style:
                                        Theme.of(context).textTheme.bodySmall),
                                const SizedBox(height: 24),
                                AnalysisReport(
                                    key: ValueKey('report-$_viewVersion'),
                                    data: data,
                                    repository: _repository,
                                    onPlanDirtyChanged: (dirty) {
                                      if (mounted) {
                                        setState(() => _planDirty = dirty);
                                      }
                                    }),
                                const SizedBox(height: 24),
                                Wrap(spacing: 12, runSpacing: 12, children: [
                                  FilledButton.icon(
                                      onPressed: () => _openRoute('/upload'),
                                      icon: const Icon(
                                          Icons.upload_file_outlined),
                                      label: const Text('วิเคราะห์คลิปใหม่')),
                                  OutlinedButton.icon(
                                      onPressed: () => _openRoute('/history'),
                                      icon:
                                          const Icon(Icons.bookmarks_outlined),
                                      label: const Text('รายการไอเดียของฉัน')),
                                  OutlinedButton.icon(
                                      onPressed: () => _openRoute('/dashboard'),
                                      icon: const Icon(Icons.home_outlined),
                                      label: const Text('กลับ Dashboard')),
                                ]),
                              ])),
        ));
  }
}

class AnalysisReport extends StatelessWidget {
  const AnalysisReport(
      {super.key,
      required this.data,
      this.repository,
      this.onPlanDirtyChanged});
  final AnalysisResultViewData data;
  final ContentRepository? repository;
  final ValueChanged<bool>? onPlanDirtyChanged;

  @override
  Widget build(BuildContext context) {
    final recommendation = data.recommendation;
    final classification = recommendation.classification;
    final withheld = classification?.isUnknown == true;
    final bundle = recommendation.evidenceBundle;
    final actions = recommendation.actionableRecommendations;
    final actionTopics = {
      for (final topic
          in (bundle['action_topics'] as List? ?? []).whereType<Map>())
        topic['topic_id'].toString(): topic,
    };
    final adviceKeywords = [
      for (final advice in actions?.items ?? <ActionableAdvice>[])
        KeywordScore(
          keyword: advice.title,
          score: 0,
          supportCount:
              (actionTopics[advice.evidenceTopicId]?['support_count'] as num?)
                      ?.toInt() ??
                  0,
          sampleSize:
              (actionTopics[advice.evidenceTopicId]?['sample_size'] as num?)
                      ?.toInt() ??
                  0,
          supportingDatasetRowIds: (actionTopics[advice.evidenceTopicId]
                      ?['supporting_dataset_row_ids'] as List? ??
                  [])
              .whereType<num>()
              .map((id) => id.toInt())
              .toList(),
        ),
    ];
    final adviceLabels = {
      for (final advice in actions?.items ?? <ActionableAdvice>[])
        if (actionTopics[advice.evidenceTopicId]?['canonical_topic'] is String)
          actionTopics[advice.evidenceTopicId]!['canonical_topic'].toString():
              advice.title,
    };
    final openingKeywords = recommendation.hookKeywords
        .where(
            (word) => actions == null || adviceLabels.containsKey(word.keyword))
        .toList();
    final topicEvidence = actions == null
        ? bundle
        : <String, dynamic>{
            ...bundle,
            'topics': bundle['action_topics'] ?? const [],
            'recommendations': const [],
            'canonicalization': 'curated_synonyms',
            'method_version': actions.methodVersion,
            'synonym_version': actions.catalogHash,
          };
    final foundTopics = (topicEvidence['topics'] as List? ?? const [])
        .whereType<Map>()
        .where((topic) => (topic['user'] as Map?)?['status'] == 'detected')
        .map((topic) =>
            (topic['title_th'] ?? topic['canonical_topic']).toString())
        .toSet()
        .toList();
    final canPlan = repository != null &&
        data.saved &&
        data.contentId != null &&
        data.raw['analysis_id'] != null;
    final input = bundle['input'] as Map? ?? const {};
    final inputUnassessable =
        input.isNotEmpty && input['availability'] != 'available';
    final hookUnassessable = inputUnassessable ||
        (bundle.isNotEmpty &&
            ((input['segments'] as List? ?? []).isEmpty ||
                input['hook_seconds'] == null));
    final domain = classification?.displayCategory ?? recommendation.domain;
    final evidence = recommendation.evidence;
    final duration = recommendation.duration;
    final medianDuration =
        duration.medianSeconds ?? duration.recommendedSeconds;
    final rangeLow = duration.percentileLowSeconds;
    final rangeHigh = duration.percentileHighSeconds;
    final hasDurationRange = rangeLow != null &&
        rangeHigh != null &&
        rangeLow > 0 &&
        rangeHigh >= rangeLow;
    final hasReference = recommendation.datasetProfile.sampleSize > 0;
    final supported = <String, KeywordScore>{
      for (final item in [
        ...recommendation.missingKeywords,
        ...recommendation.hookKeywords
      ])
        if (item.hasDatasetEvidence) item.keyword: item,
    };
    final revisionComparison = data.raw['revision_comparison'] is Map
        ? Map<String, dynamic>.from(data.raw['revision_comparison'] as Map)
        : null;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      if (revisionComparison != null) ...[
        RevisionComparisonPanel(
            data: revisionComparison,
            onOpenParent: repository == null
                ? null
                : () {
                    final parent = revisionComparison['parent'] as Map?;
                    final contentId = (parent?['content_id'] as num?)?.toInt();
                    if (contentId != null) {
                      Navigator.pushNamed(context, '/result',
                          arguments: ResultScreenArgs(contentId: contentId));
                    }
                  }),
        const SizedBox(height: 24),
      ],
      _Band(
          title: '1. พบอะไรในคลิป',
          icon: Icons.fact_check_outlined,
          children: [
            Text('หมวดหมู่ของคลิป: $domain',
                style: Theme.of(context).textTheme.titleMedium),
            if (classification != null)
              Text(
                  classification.isUnknown
                      ? 'ยังไม่ยืนยันหมวดหมู่สำหรับสร้างคำแนะนำ'
                      : 'ความมั่นใจของโมเดล ${(classification.confidence * 100).toStringAsFixed(0)}% ไม่ใช่คะแนนคุณภาพคลิป',
                  style: Theme.of(context).textTheme.bodySmall),
            if (classification?.warning.isNotEmpty == true)
              Text(classification!.warning),
            const SizedBox(height: 12),
            Text(inputUnassessable
                ? 'ข้อความถอดเสียงยังไม่สมบูรณ์ จึงยังสรุปประเด็นในคลิปไม่ได้'
                : foundTopics.isNotEmpty
                    ? 'ในข้อความถอดเสียงพบประเด็น: ${foundTopics.join(' / ')}'
                    : actions == null
                        ? 'ผลรุ่นนี้ไม่มีสรุปหัวข้อแบบใหม่ สามารถเปิดดูข้อมูลที่บันทึกไว้ด้านล่าง'
                        : 'ยังไม่มีข้อมูลเพียงพอที่จะสรุปประเด็นในคลิปนี้'),
            if (bundle['origin'] == 'historical_legacy_no_snapshot')
              const Padding(
                  padding: EdgeInsets.only(top: 12),
                  child: Text(
                      'ผลเก่าไม่มีหลักฐานบันทึกครบ แสดงข้อมูลเดิมโดยไม่คำนวณคำแนะนำใหม่')),
            if (classification?.isUnknown == true &&
                classification!.rawTaxonomyLeafKey.isNotEmpty)
              ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  title: const Text('ผลทายก่อนตรวจรับ'),
                  children: [
                    Text('${classification.rawTaxonomyLeafKey} · '
                        'ความมั่นใจภายในโมเดล ${(classification.confidence * 100).toStringAsFixed(1)}%'),
                    const Text(
                        'ผลนี้ยังไม่ผ่านเกณฑ์ จึงไม่ใช้เลือกคลิปอ้างอิงหรือสร้างคำแนะนำ'),
                  ]),
            ExpansionTile(
                tilePadding: EdgeInsets.zero,
                title: const Text('คำสำคัญและข้อความถอดเสียง'),
                children: [
                  _Words(
                      title: 'คำสำคัญที่พบทั้งคลิป',
                      words: recommendation.contentKeywords,
                      empty: inputUnassessable
                          ? 'ตรวจคำสำคัญไม่ได้ เพราะข้อความถอดเสียงไม่สมบูรณ์'
                          : 'ยังไม่พบคำสำคัญจากเนื้อหาในคลิปนี้'),
                  _Words(
                      title: 'คำสำคัญที่พบในช่วงเปิดคลิป',
                      words: recommendation.hookTerms,
                      empty: hookUnassessable
                          ? 'ตรวจช่วงเปิดไม่ได้ เพราะไม่มีข้อความถอดเสียงพร้อมเวลาที่เพียงพอ'
                          : 'ยังไม่พบคำสำคัญจากเสียงพูดในช่วงเปิดคลิป'),
                  _Words(
                      title: 'หัวข้อหลักที่ใช้เปรียบเทียบ',
                      words: recommendation.comparableKeywords,
                      empty: 'ยังไม่พบหัวข้อที่ระบบรู้จักสำหรับใช้เปรียบเทียบ'),
                  ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      title: const Text('ข้อความถอดเสียง'),
                      children: [
                        _Transcript(
                            label: 'ข้อความต้นฉบับ',
                            text: data.rawTranscript.isEmpty
                                ? data.transcript
                                : data.rawTranscript),
                        _Transcript(
                            label: 'ข้อความหลังปรับศัพท์',
                            text: data.cleanedTranscript.isEmpty
                                ? data.transcript
                                : data.cleanedTranscript),
                      ]),
                ]),
          ]),
      const SizedBox(height: 24),
      _Band(title: '2. ควรเพิ่มอะไร', icon: Icons.lightbulb_outline, children: [
        if (!withheld && !inputUnassessable) ...[
          _Suggestions(
              title: actions == null
                  ? 'คำแนะนำที่บันทึกไว้เดิม'
                  : 'คำสำคัญที่แนะนำให้เพิ่ม',
              words: actions == null
                  ? recommendation.missingKeywords
                  : adviceKeywords,
              empty: actions == null
                  ? 'ไม่มีคำแนะนำคำสำคัญบันทึกไว้'
                  : 'ยังไม่มีประเด็นเพิ่มที่มีหลักฐานเพียงพอ'),
          _Suggestions(
              title: actions == null
                  ? 'คำแนะนำช่วงเปิดที่บันทึกไว้เดิม'
                  : 'คำสำคัญที่เสนอสำหรับช่วงเปิดคลิป',
              words: openingKeywords,
              labels: adviceLabels,
              empty: actions == null
                  ? 'ไม่มีคำแนะนำช่วงเปิดบันทึกไว้'
                  : 'ยังไม่มีข้อเสนอช่วงเปิดที่มีหลักฐานเพียงพอ'),
        ],
        if (inputUnassessable)
          const Text(
              'งดข้อเสนอให้เพิ่มหัวข้อ เพราะข้อความถอดเสียงไม่สมบูรณ์ จึงยังสรุปไม่ได้ว่าผู้ใช้ไม่ได้พูดเรื่องนั้น'),
        if (withheld)
          const Padding(
              padding: EdgeInsets.only(bottom: 12),
              child: Text(
                  'งดคำแนะนำเฉพาะหมวด เพราะผลจำแนกยังไม่ผ่านเกณฑ์ตรวจรับ')),
        if (canPlan)
          ClipRevisionPlanner(
              data: data,
              repository: repository!,
              onDirtyChanged: onPlanDirtyChanged,
              withheld: withheld || inputUnassessable)
        else if (actions != null)
          ActionableAdvicePanel(
              data: actions,
              bundle: bundle,
              withheld: withheld || inputUnassessable)
        else
          const Text(
              'ผลรุ่นนี้ยังไม่มีคำแนะนำแบบลงมือทำ ข้อมูลคำแนะนำเดิมยังเปิดดูได้ในส่วนรายละเอียด'),
        if (!canPlan)
          const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Text(
                  'ยังบันทึกแผนไม่ได้จนกว่าจะมีผลวิเคราะห์ที่บันทึกและตรวจสอบต้นฉบับได้')),
        const Divider(),
        Text('ความยาวคลิปที่แนะนำ',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Text(withheld
            ? 'งดแนะนำความยาวจนกว่าจะยืนยันหมวดหมู่ได้'
            : duration.hasSufficientEvidence &&
                    medianDuration != null &&
                    medianDuration > 0
                ? 'ค่ากลาง $medianDuration วินาที · ${hasDurationRange ? 'ช่วง $rangeLow–$rangeHigh วินาที' : 'ไม่ได้บันทึกช่วงความยาว'}'
                : 'ข้อมูลอ้างอิงยังไม่เพียงพอ'),
        Text(
            'มีข้อมูลความยาว ${duration.sampleSize} คลิป · ขั้นต่ำ ${duration.minimumSampleSize} คลิป',
            style: Theme.of(context).textTheme.bodySmall),
        const Divider(),
        CurrentTrendIdeasPanel(data: recommendation.currentTrendIdeas),
      ]),
      const SizedBox(height: 24),
      _Band(
          title: '3. เพราะอะไรจึงแนะนำ',
          icon: Icons.manage_search_outlined,
          children: [
            ExpansionTile(
                tilePadding: EdgeInsets.zero,
                title: const Text('เปิดดูหลักฐานและเวอร์ชัน'),
                children: [
                  Text(withheld
                      ? 'ผลจำแนกยังไม่ผ่านเกณฑ์ ระบบจึงไม่เลือก Dataset มาอ้างอิงในรอบนี้'
                      : hasReference
                          ? 'เปรียบเทียบกับคลิปอ้างอิงหมวดเดียวกัน ${recommendation.datasetProfile.sampleSize} คลิป '
                              'โดยดูจำนวนคลิปที่กล่าวถึง ความถี่ และผลตอบรับของคลิป'
                          : 'ยังไม่มีคลิปอ้างอิงที่ผ่านเกณฑ์เพียงพอ จึงยังสรุปคำแนะนำไม่ได้'),
                  const SizedBox(height: 8),
                  const Text(
                      'ความสัมพันธ์ในคลิปอ้างอิงไม่ยืนยันว่าเพิ่มหัวข้อแล้วจะทำให้ยอดวิวหรือยอดไลก์เพิ่มขึ้น'),
                  if (evidence.warning?.isNotEmpty == true)
                    Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Text(evidence.warning!)),
                  if (bundle.isNotEmpty)
                    RecommendationEvidencePanel(bundle: topicEvidence)
                  else
                    for (final keyword in supported.values)
                      _KeywordEvidence(item: keyword),
                  if (supported.isEmpty && bundle.isEmpty)
                    const Padding(
                        padding: EdgeInsets.symmetric(vertical: 12),
                        child: Text(
                            'ยังไม่มีหลักฐานรายหัวข้อที่เปิดดูได้ในผลนี้')),
                  ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      title: const Text('หลักฐานความยาวคลิป'),
                      children: [
                        Align(
                            alignment: Alignment.centerLeft,
                            child: Padding(
                                padding: const EdgeInsets.only(bottom: 16),
                                child: Text(
                                    'จำนวนตัวอย่าง ${duration.sampleSize} คลิป\n'
                                    'ช่วงเปอร์เซ็นไทล์ ${duration.percentileLow}–${duration.percentileHigh}\n'
                                    'Dataset IDs: ${evidence.durationDatasetRowIds.isEmpty ? "ยังไม่มี" : evidence.durationDatasetRowIds.join(", ")}\n'
                                    '${evidence.durationExplanation}')))
                      ]),
                  AnalysisSettingsAudit(snapshot: data.analysisSettings),
                ]),
          ]),
    ]);
  }
}

class _Band extends StatelessWidget {
  const _Band(
      {required this.title, required this.icon, required this.children});
  final String title;
  final IconData icon;
  final List<Widget> children;
  @override
  Widget build(BuildContext context) => Semantics(
      container: true,
      explicitChildNodes: true,
      child: ColoredBox(
          color: Theme.of(context).colorScheme.surface,
          child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(children: [
                      Icon(icon, color: Theme.of(context).colorScheme.primary),
                      const SizedBox(width: 12),
                      Expanded(
                          child: Semantics(
                              header: true,
                              child: Text(title,
                                  style:
                                      Theme.of(context).textTheme.titleLarge)))
                    ]),
                    const Divider(height: 32),
                    ...children,
                  ]))));
}

class _Words extends StatelessWidget {
  const _Words({required this.title, required this.words, required this.empty});
  final String title, empty;
  final List<String> words;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(title, style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        if (words.isEmpty)
          Text(empty)
        else
          Wrap(
              spacing: 8,
              runSpacing: 8,
              children: words
                  .map((word) => Chip(label: Text(word, softWrap: true)))
                  .toList()),
      ]));
}

class _Suggestions extends StatelessWidget {
  const _Suggestions(
      {required this.title,
      required this.words,
      required this.empty,
      this.labels = const {}});
  final String title, empty;
  final List<KeywordScore> words;
  final Map<String, String> labels;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(title, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (words.isEmpty) Text(empty),
        for (final word in words)
          Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child:
                  Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Icon(Icons.add_circle_outline, size: 20),
                const SizedBox(width: 10),
                Expanded(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                      Text(labels[word.keyword] ?? word.keyword,
                          style: Theme.of(context).textTheme.titleSmall),
                      if (word.hasDatasetEvidence)
                        Text(
                            'พบใน ${word.supportCount} จาก ${word.sampleSize} คลิปอ้างอิง',
                            style: Theme.of(context).textTheme.bodySmall),
                    ])),
              ])),
      ]));
}

class _Transcript extends StatelessWidget {
  const _Transcript({required this.label, required this.text});
  final String label, text;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(label, style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        SelectableText(text.isEmpty ? 'ไม่มีข้อความถอดเสียงในผลนี้' : text),
      ]));
}

class _KeywordEvidence extends StatelessWidget {
  const _KeywordEvidence({required this.item});
  final KeywordScore item;
  Future<void> _open(BuildContext context, String url) async {
    final uri = Uri.tryParse(url);
    try {
      if (uri == null ||
          !['https', 'http'].contains(uri.scheme) ||
          uri.host.isEmpty ||
          !await launchUrl(uri, mode: LaunchMode.externalApplication)) {
        throw StateError('invalid source');
      }
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('เปิดต้นทางไม่สำเร็จ')));
      }
    }
  }

  @override
  Widget build(BuildContext context) => ExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: Text('หลักฐาน: ${item.keyword}'),
          subtitle: Text(
              '${item.supportCount}/${item.sampleSize} คลิป · กล่าวถึงรวม ${item.totalFrequency} ครั้ง'),
          children: [
            Align(
                alignment: Alignment.centerLeft,
                child: SelectableText(
                    'Dataset IDs: ${item.supportingDatasetRowIds.join(", ")}')),
            for (final source in item.supportingExamples)
              ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(source.title),
                  subtitle: Text(
                      'ข้อมูล #${source.datasetId} · กล่าวถึง ${source.frequency} ครั้ง\n'
                      'เก็บสถิติ: ${trendIdeaTime(source.statisticsCapturedAt)} · เผยแพร่: ${trendIdeaTime(source.publishedAt)}'),
                  trailing: source.videoUrl.isEmpty
                      ? null
                      : IconButton(
                          tooltip: 'เปิดคลิปอ้างอิง #${source.datasetId}',
                          onPressed: () => _open(context, source.videoUrl),
                          icon: const Icon(Icons.open_in_new))),
          ]);
}
