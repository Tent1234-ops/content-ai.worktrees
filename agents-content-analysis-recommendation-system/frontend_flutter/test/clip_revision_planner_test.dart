import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:content_ai_web/models/clip_revision_plan.dart';
import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/repositories/content_repository.dart';
import 'package:content_ai_web/screens/result_screen.dart';
import 'package:content_ai_web/widgets/clip_revision_planner.dart';

AnalysisResultViewData fixture() => AnalysisResultViewData.fromJson({
      'content_id': 41,
      'analysis_id': 81,
      'recommendation_fingerprint': 'a' * 64,
      'title': 'Test fixture',
      'transcript': 'รีวิวแบตเตอรี่',
      'recommendation': {
        'domain': 'phone',
        'content_keywords': ['RAW KEYWORD'],
        'actionable_recommendations': {
          'status': 'ready',
          'items': [
            {
              'id': 'charging',
              'evidence_topic_id': 'charge',
              'title': 'ความเร็วในการชาร์จ',
              'finding': 'พบเรื่องแบตเตอรี่',
              'proposal': 'ทดลองจับเวลาชาร์จ',
              'condition': 'ตรวจอุปกรณ์ที่รองรับก่อน',
              'steps': ['บันทึกเวลาจริง'],
              'example': 'ผมจะลองจับเวลาและรายงานสิ่งที่วัดได้',
              'reason': 'มีหลักฐานจากคลิปอ้างอิง',
            }
          ],
        },
        'evidence_bundle': {
          'input': {'availability': 'available'},
          'action_topics': [
            {
              'topic_id': 'battery',
              'title_th': 'แบตเตอรี่',
              'user': {'status': 'detected'},
              'canonical_topic': 'battery life',
              'references': [],
            }
          ]
        },
      },
    });

class PlanRepository extends ContentRepository {
  ClipRevisionPlan stored = ClipRevisionPlan(
      contentId: 41,
      analysisId: 81,
      fingerprint: 'a' * 64,
      revision: 0,
      selectedIds: [],
      notes: '');
  int saves = 0, reads = 0;
  bool fail = false, loadFail = false, invalidReply = false;
  Completer<void>? gate;
  @override
  Future<ClipRevisionPlan> getRevisionPlan(int contentId) async {
    reads++;
    if (loadFail) throw Exception('offline');
    return stored;
  }

  @override
  Future<ClipRevisionPlan> saveRevisionPlan(
      int contentId, Map<String, dynamic> body) async {
    saves++;
    if (gate != null) await gate!.future;
    if (fail) throw Exception('บันทึกไม่สำเร็จ');
    if (invalidReply) return stored;
    stored = ClipRevisionPlan(
        contentId: 41,
        analysisId: 81,
        fingerprint: 'a' * 64,
        revision: stored.revision + 1,
        selectedIds: List<String>.from(body['selected_advice_ids']),
        notes: body['notes'],
        savedAt: DateTime.utc(2026, 9, 29));
    return stored;
  }
}

Future<void> mount(WidgetTester tester, PlanRepository repo) async {
  await tester.binding.setSurfaceSize(const Size(1100, 1000));
  await tester.pumpWidget(MaterialApp(
      home: Scaffold(
          body: SingleChildScrollView(
              child: ClipRevisionPlanner(data: fixture(), repository: repo)))));
  await tester.pumpAndSettle();
}

Future<void> edit(WidgetTester tester) async {
  await tester
      .ensureVisible(find.byKey(const ValueKey('select-advice-charging')));
  await tester.tap(find.byKey(const ValueKey('select-advice-charging')));
  await tester.pump();
  await tester.ensureVisible(find.byKey(const ValueKey('revision-plan-notes')));
  await tester.enterText(find.byKey(const ValueKey('revision-plan-notes')),
      'ทดสอบด้วยอุปกรณ์ที่รองรับ');
  await tester.pump();
}

Future<void> save(WidgetTester tester) async {
  await tester.ensureVisible(find.byKey(const ValueKey('save-revision-plan')));
  await tester.tap(find.byKey(const ValueKey('save-revision-plan')));
  await tester.pump();
}

void main() {
  for (final revision in [0, 1]) {
    testWidgets(
        'result hides the entire planner and leaves stored plan untouched: revision=$revision',
        (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 900));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final repo = PlanRepository()
        ..stored = ClipRevisionPlan(
            contentId: 41,
            analysisId: 81,
            fingerprint: 'a' * 64,
            revision: revision,
            selectedIds: revision == 0 ? const [] : const ['charging'],
            notes: revision == 0 ? '' : 'Existing private notes');
      final original = repo.stored;
      await tester.pumpWidget(MaterialApp(
          home: Scaffold(
              body: SingleChildScrollView(
                  child: AnalysisReport(data: fixture(), repository: repo)))));
      await tester.pumpAndSettle();
      expect(find.byType(ClipRevisionPlanner), findsNothing);
      expect(find.text('แผนปรับคลิปของฉัน'), findsNothing);
      expect(find.text('เลือกนำไปปรับ'), findsNothing);
      expect(find.text('รายละเอียดแผนปรับคลิป'), findsNothing);
      expect(find.text('บันทึกแผนปรับคลิป'), findsNothing);
      expect(find.text('โหลดแผนที่บันทึก'), findsNothing);
      expect(find.text('อัปโหลดฉบับแก้ไข'), findsNothing);
      expect(find.byKey(const ValueKey('copy-advice-charging')), findsNothing);
      expect(find.byTooltip('คัดลอกประโยคตัวอย่าง'), findsNothing);
      expect(find.text('เปิดดูหลักฐานและเวอร์ชัน'), findsNothing);
      expect(repo.reads, 0);
      expect(repo.saves, 0);
      expect(identical(repo.stored, original), isTrue);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets(
      'selection is a draft, save waits for confirmation and reopening restores it',
      (tester) async {
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repo = PlanRepository()..gate = Completer<void>();
    await mount(tester, repo);
    await edit(tester);
    expect(repo.saves, 0);
    expect(
        find.textContaining('ยังไม่ได้ยืนยันว่าปรับคลิปเสร็จ'), findsOneWidget);
    expect(find.text('มีการเปลี่ยนแปลงที่ยังไม่บันทึก'), findsOneWidget);
    await save(tester);
    expect(find.text('บันทึกแผนปรับคลิปแล้ว'), findsNothing);
    expect(
        tester
            .widget<FilledButton>(
                find.byKey(const ValueKey('save-revision-plan')))
            .onPressed,
        isNull);
    repo.gate!.complete();
    await tester.pumpAndSettle();
    expect(find.text('บันทึกแผนปรับคลิปแล้ว'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await mount(tester, repo);
    expect(
        tester
            .widget<CheckboxListTile>(
                find.byKey(const ValueKey('select-advice-charging')))
            .value,
        isTrue);
    expect(
        tester
            .widget<TextField>(
                find.byKey(const ValueKey('revision-plan-notes')))
            .controller!
            .text,
        'ทดสอบด้วยอุปกรณ์ที่รองรับ');
    expect(find.text('มีการเปลี่ยนแปลงที่ยังไม่บันทึก'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  for (final invalidReply in [false, true]) {
    testWidgets(
        'failed or mismatched response keeps the draft: invalid=$invalidReply',
        (tester) async {
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final repo = PlanRepository()
        ..fail = !invalidReply
        ..invalidReply = invalidReply;
      await mount(tester, repo);
      await edit(tester);
      await save(tester);
      await tester.pumpAndSettle();
      expect(find.text('บันทึกแผนปรับคลิปแล้ว'), findsNothing);
      expect(find.textContaining('ยังยืนยันการบันทึกไม่ได้'), findsOneWidget);
      expect(
          tester
              .widget<TextField>(
                  find.byKey(const ValueKey('revision-plan-notes')))
              .controller!
              .text,
          'ทดสอบด้วยอุปกรณ์ที่รองรับ');
      expect(repo.stored.revision, 0);
      repo.fail = false;
      repo.invalidReply = false;
      await save(tester);
      await tester.pumpAndSettle();
      expect(repo.stored.revision, 1);
    });
  }

  testWidgets('load failure disables writes and retry restores access',
      (tester) async {
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repo = PlanRepository()..loadFail = true;
    await mount(tester, repo);
    expect(find.textContaining('โหลดแผนไม่สำเร็จ'), findsOneWidget);
    expect(
        tester
            .widget<CheckboxListTile>(
                find.byKey(const ValueKey('select-advice-charging')))
            .onChanged,
        isNull);
    expect(
        tester
            .widget<FilledButton>(
                find.byKey(const ValueKey('save-revision-plan')))
            .onPressed,
        isNull);
    repo.loadFail = false;
    await tester.tap(find.text('โหลดแผนอีกครั้ง'));
    await tester.pumpAndSettle();
    expect(find.textContaining('โหลดแผนไม่สำเร็จ'), findsNothing);
  });

  testWidgets(
      'advice keeps the example without copy controls or clipboard calls',
      (tester) async {
    addTearDown(() => tester.binding.setSurfaceSize(null));
    int clipboardWrites = 0;
    tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') {
        clipboardWrites++;
      }
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null));
    await mount(tester, PlanRepository());
    expect(find.text('ผมจะลองจับเวลาและรายงานสิ่งที่วัดได้'), findsOneWidget);
    expect(find.byKey(const ValueKey('copy-advice-charging')), findsNothing);
    expect(find.byTooltip('คัดลอกประโยคตัวอย่าง'), findsNothing);
    expect(clipboardWrites, 0);
    expect(find.text('คัดลอกประโยคตัวอย่างแล้ว'), findsNothing);
  });

  testWidgets('summary shows keywords while evidence is in a separate tab',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(
                child: AnalysisReport(data: fixture())))));
    expect(find.textContaining('ในข้อความถอดเสียงพบประเด็น: แบตเตอรี่'),
        findsOneWidget);
    expect(find.text('RAW KEYWORD'), findsOneWidget);
    expect(find.text('เวอร์ชันและเวลาของหลักฐาน'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  for (final width in [390.0, 1440.0]) {
    testWidgets('result hides normalized transcript and audit UI at $width',
        (tester) async {
      await tester.binding.setSurfaceSize(Size(width, 900));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final data = AnalysisResultViewData.fromJson({
        ...fixture().raw,
        'raw_transcript': 'ORIGINAL SPEECH',
        'cleaned_transcript': 'NORMALIZED INTERNAL TEXT',
      });
      await tester.pumpWidget(MaterialApp(
          home: Scaffold(
              body: SingleChildScrollView(child: AnalysisReport(data: data)))));
      final tab = find.byKey(const ValueKey('result-tab-transcript'));
      await tester.ensureVisible(tab);
      await tester.tap(tab);
      await tester.pumpAndSettle();
      expect(find.text('ORIGINAL SPEECH'), findsOneWidget);
      expect(find.text('ข้อความหลังปรับศัพท์'), findsNothing);
      expect(find.text('NORMALIZED INTERNAL TEXT'), findsNothing);
      expect(find.text('เปิดดูหลักฐานและเวอร์ชัน'), findsNothing);
      expect(data.cleanedTranscript, 'NORMALIZED INTERNAL TEXT');
      expect(tester.takeException(), isNull);
    });
  }

  test('empty HTTP success body is not a valid saved plan', () {
    expect(() => ClipRevisionPlan.fromJson({}), throwsFormatException);
  });

  testWidgets(
      'saved plan enables revision upload and dirty draft requires confirmation',
      (tester) async {
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repo = PlanRepository()
      ..stored = ClipRevisionPlan(
          contentId: 41,
          analysisId: 81,
          fingerprint: 'a' * 64,
          revision: 1,
          selectedIds: const ['charging'],
          notes: 'แผนที่บันทึกแล้ว',
          savedAt: DateTime.utc(2026, 9, 29));
    await mount(tester, repo);
    final upload = find.byKey(const ValueKey('upload-revision'));
    expect(tester.widget<FilledButton>(upload).onPressed, isNotNull);
    await tester.enterText(find.byKey(const ValueKey('revision-plan-notes')),
        'ฉบับร่างที่ยังไม่บันทึก');
    await tester.pump();
    await tester.tap(upload);
    await tester.pumpAndSettle();
    expect(find.text('แผนฉบับร่างยังไม่ถูกบันทึก'), findsOneWidget);
    expect(find.text('ใช้แผนที่บันทึกไว้'), findsOneWidget);
  });

  testWidgets(
      'notes-only saved plan explains automatic comparison is unavailable',
      (tester) async {
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repo = PlanRepository()
      ..stored = ClipRevisionPlan(
          contentId: 41,
          analysisId: 81,
          fingerprint: 'a' * 64,
          revision: 1,
          selectedIds: const [],
          notes: 'แก้ตามบันทึกส่วนตัว',
          savedAt: DateTime.utc(2026, 9, 29));
    await mount(tester, repo);
    expect(find.textContaining('แผนนี้มีเฉพาะบันทึก'), findsOneWidget);
  });
}
