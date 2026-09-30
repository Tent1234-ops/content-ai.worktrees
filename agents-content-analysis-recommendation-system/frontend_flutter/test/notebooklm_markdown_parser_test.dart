import 'package:content_ai_web/utils/notebooklm_markdown_parser.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const longTranscript =
      'วันนี้เราจะมารีวิวโทรศัพท์จอพับรุ่นใหม่ โดยทดสอบหน้าจอ กล้อง '
      'แบตเตอรี่ ประสิทธิภาพ และการใช้งานจริงตลอดทั้งวันอย่างละเอียด';

  test('extracts the NotebookLM cleaned transcript without metadata', () {
    final document = NotebookLmMarkdownParser.parse('''
# Phone Review Transcript (Cleaned for AI Training)

## Metadata
- **Source Video:** Galaxy Phone Review
- **Creator Channel:** Example Channel
- **Source URL:** https://www.youtube.com/watch?v=abcdefghijk

---

## Cleaned Transcription Text

$longTranscript
''');

    expect(document.transcript, longTranscript);
    expect(document.sourceTitle, 'Galaxy Phone Review');
    expect(document.creatorChannel, 'Example Channel');
    expect(
      document.sourceUrl,
      'https://www.youtube.com/watch?v=abcdefghijk',
    );
    expect(document.transcript, isNot(contains('## Metadata')));
  });

  test('supports Thai transcript headings and stops at the next section', () {
    final document = NotebookLmMarkdownParser.parse('''
# เอกสารถอดเสียง

## ข้อความถอดเสียง
$longTranscript

### กล้องและการถ่ายวิดีโอ
$longTranscript

## Notes
This must not enter the training transcript.
''');

    expect(document.transcript, contains('### กล้องและการถ่ายวิดีโอ'));
    expect(document.transcript, contains(longTranscript));
    expect(document.transcript, isNot(contains('Notes')));
  });

  test('accepts NotebookLM Video Link metadata', () {
    final document = NotebookLmMarkdownParser.parse('''
## Metadata
- **Video Link:** https://youtu.be/nG3ITcW2vTg?si=example

## Cleaned Transcription Text
$longTranscript
''');

    expect(
      document.sourceUrl,
      'https://youtu.be/nG3ITcW2vTg?si=example',
    );
  });

  test('uses Title metadata instead of a generic document heading', () {
    final document = NotebookLmMarkdownParser.parse('''
# Video Transcript
**Title:** Actual Laptop Review
**URL:** https://youtube.com/shorts/Av8HhwCqigU

## Transcript Content
$longTranscript
''');

    expect(document.sourceTitle, 'Actual Laptop Review');
    expect(
      document.sourceUrl,
      'https://youtube.com/shorts/Av8HhwCqigU',
    );
  });

  test('accepts Direct Link metadata and Transcript Content heading', () {
    final document = NotebookLmMarkdownParser.parse('''
# Laptop buying guide
- **Direct Link**: https://youtu.be/JuwQbcLDASI?si=example
- **YouTube Video ID**: JuwQbcLDASI

## Transcript Content
$longTranscript
''');

    expect(document.sourceUrl, 'https://youtu.be/JuwQbcLDASI?si=example');
    expect(document.transcript, longTranscript);
  });

  test('extracts a URL from Markdown link metadata without a heading', () {
    final document = NotebookLmMarkdownParser.parse('''
# Laptop review
**Direct Link:** [https://youtu.be/iD93x8k06J4?si=example](https://youtu.be/iD93x8k06J4?si=example)
**YouTube Video ID:** `iD93x8k06J4`

$longTranscript
''');

    expect(document.sourceUrl, 'https://youtu.be/iD93x8k06J4?si=example');
    expect(document.transcript, longTranscript);
  });

  test('accepts a descriptive heading ending with Transcript', () {
    final document = NotebookLmMarkdownParser.parse('''
# Laptop review
**Video Link**: https://youtu.be/8aDiCPpMKRc?si=example

## Source transcription (Transcript)
$longTranscript
''');

    expect(document.sourceUrl, 'https://youtu.be/8aDiCPpMKRc?si=example');
    expect(document.transcript, longTranscript);
  });

  test('accepts compact Thai metadata followed directly by transcript', () {
    final document = NotebookLmMarkdownParser.parse('''
# รีวิวกล้อง Canon EOS R50V
**ช่อง:** Camera Example
**ลิงก์วิดีโอ:** https://youtu.be/bgtxAFTUS1w?si=example

$longTranscript
''');

    expect(document.sourceTitle, 'รีวิวกล้อง Canon EOS R50V');
    expect(document.creatorChannel, 'Camera Example');
    expect(
      document.sourceUrl,
      'https://youtu.be/bgtxAFTUS1w?si=example',
    );
    expect(document.transcript, longTranscript);
  });

  test('removes a code fence around the transcript', () {
    final document = NotebookLmMarkdownParser.parse('''
## Full source transcript
```text
$longTranscript
```
''');

    expect(document.transcript, longTranscript);
  });

  test('rejects Markdown without a recognized transcript section', () {
    expect(
      () => NotebookLmMarkdownParser.parse('''
# Summary
$longTranscript
'''),
      throwsFormatException,
    );
  });

  test('rejects a transcript that is too short', () {
    expect(
      () => NotebookLmMarkdownParser.parse('''
## Transcript
Short text.
'''),
      throwsFormatException,
    );
  });

  test('keeps all segment text without treating numbered headings as speech',
      () {
    final document = NotebookLmMarkdownParser.parse('''
# Transcript: Display title only
- **Video Link:** https://youtu.be/abcdefghijk
- **YouTube Video ID:** `abcdefghijk`

### Segment 1
$longTranscript
### Segment 2
$longTranscript
''');
    expect(document.transcript, '$longTranscript\n$longTranscript');
    expect(document.transcript, isNot(contains('Display title')));
    expect(document.sourceVideoId, 'abcdefghijk');
  });

  test('rejects a missing-transcript notice even if padded past minimum length',
      () {
    expect(() => NotebookLmMarkdownParser.parse('''
# Transcript: No captions
- **Video Link:** https://youtu.be/abcdefghijk
### Segment 1
[ไม่พบคำบรรยาย/Transcript ในระบบ YouTube สำหรับคลิปวิดีโอนี้]
${'Additional notice. ' * 10}
'''), throwsFormatException);
  });
}
