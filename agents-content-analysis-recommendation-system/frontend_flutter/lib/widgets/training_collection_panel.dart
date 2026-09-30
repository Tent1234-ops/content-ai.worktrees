import 'package:flutter/material.dart';
import '../models/model_training.dart';
import '../repositories/admin_repository.dart';

class TrainingCollectionPanel extends StatefulWidget {
  const TrainingCollectionPanel(
      {super.key, required this.plan, required this.repository});
  final Map<String, dynamic> plan;
  final AdminRepository repository;

  @override
  State<TrainingCollectionPanel> createState() =>
      _TrainingCollectionPanelState();
}

class _TrainingCollectionPanelState extends State<TrainingCollectionPanel> {
  final _channels = TextEditingController();
  List<Map<String, dynamic>> _preview = [];
  bool _checking = false;
  String? _error;

  @override
  void dispose() {
    _channels.dispose();
    super.dispose();
  }

  String _split(String value) => switch (value) {
        'train' => 'ฝึก (Train)',
        'validation' => 'เลือกเกณฑ์ (Validation)',
        'test' => 'ทดสอบ (Test)',
        _ => value,
      };

  Future<void> _check() async {
    final ids = _channels.text
        .trim()
        .split(RegExp(r'[\s,]+'))
        .where((id) => id.isNotEmpty)
        .toList();
    setState(() {
      _error = null;
      _preview = [];
    });
    if (ids.isEmpty ||
        ids.length > 50 ||
        ids.any((id) => !RegExp(r'^UC[A-Za-z0-9_-]{22}$').hasMatch(id))) {
      setState(() =>
          _error = 'ต้องเป็นรหัสช่อง UC... ยาว 24 ตัวอักษร จำนวน 1–50 ช่อง');
      return;
    }
    setState(() => _checking = true);
    try {
      final result = await widget.repository.previewTrainingChannels(ids);
      if (mounted) setState(() => _preview = result);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'ตรวจชุดข้อมูลไม่สำเร็จ กรุณาลองใหม่');
      }
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final rows = trainingRows(widget.plan['rows']);
    if (rows.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text('แผนเก็บข้อมูลเพิ่ม',
          style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 8),
      Text(widget.plan['collection_ready'] == true
          ? 'จำนวนข้อมูลครบสำหรับประเมิน ยังต้องผ่านคะแนนก่อนเปิดใช้โมเดล'
          : widget.plan['additional_minimum'] == 0
              ? 'จำนวนครบ แต่คุณภาพหรือการแบ่งชุดยังไม่ผ่านเกณฑ์'
              : 'ยังขาดอย่างน้อย ${widget.plan['additional_minimum']} รายการสำหรับเกณฑ์เปิดใช้โมเดลใหม่'),
      const SizedBox(height: 8),
      SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
              columns: const [
                DataColumn(label: Text('ข้อมูล / หน้าที่')),
                DataColumn(label: Text('ใช้ได้จริง'), numeric: true),
                DataColumn(label: Text('ขั้นต่ำ'), numeric: true),
                DataColumn(label: Text('ต้องเพิ่ม'), numeric: true),
                DataColumn(label: Text('ช่อง / ขั้นต่ำ')),
              ],
              rows: rows
                  .map((row) => DataRow(cells: [
                        DataCell(Text(row['leaf_key'] == 'unknown'
                            ? 'นอกขอบเขต · ${_split(row['split'].toString())}'
                            : '${row['leaf_key']} · รวมทุกชุด')),
                        DataCell(Text('${row['current']}')),
                        DataCell(Text('${row['minimum']}')),
                        DataCell(Text(
                            '${row['additional_minimum'] ?? row['missing']}')),
                        DataCell(Text(
                            '${row['channels']} / ${row['minimum_channels']}')),
                      ]))
                  .toList())),
      const SizedBox(height: 8),
      Text(
          'Unknown ที่อยู่ชุด Train: ${widget.plan['unknown_train_reserved_count']} รายการ · ยังไม่นับเป็น Validation หรือ Test'),
      const Text('ครบจำนวนไม่รับประกันความแม่น และไม่นำชุดทดสอบไปสร้างคำแนะนำ'),
      ExpansionTile(
          tilePadding: EdgeInsets.zero,
          childrenPadding: const EdgeInsets.only(top: 12, bottom: 8),
          title: const Text('ตรวจชุดข้อมูลจากรหัสช่อง'),
          children: [
            TextField(
                controller: _channels,
                minLines: 2,
                maxLines: 4,
                enabled: !_checking,
                key: const Key('collection-channel-ids'),
                decoration: const InputDecoration(
                    labelText: 'รหัสช่อง YouTube',
                    hintText: 'UC...',
                    border: OutlineInputBorder())),
            const SizedBox(height: 12),
            Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                    key: const Key('collection-preview'),
                    onPressed: _checking ? null : _check,
                    icon: const Icon(Icons.fact_check_outlined),
                    label: Text(_checking ? 'กำลังตรวจ' : 'ตรวจชุดข้อมูล'))),
            if (_error != null)
              Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(_error!,
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.error))),
            for (final row in _preview)
              Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                          '${row['channel_id']}\n${_split(row['assigned_split'].toString())} · มีข้อมูลเดิม ${row['existing_dataset_count']} รายการ'
                          '${row['split_conflict'] == true ? '\nพบชุดข้อมูลเดิมไม่ตรงกัน ต้องตรวจแก้ก่อนนำเข้า' : ''}'
                          '${row['unknown_usage'] == 'reserved_not_used' ? '\nUnknown ของช่องนี้ไม่เติมยอด Validation/Test' : ''}'))),
            if (_preview.isNotEmpty)
              const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Text(
                      'ผลนี้ตรวจการแบ่งชุดเท่านั้น ยังไม่ยืนยันว่าช่องมีอยู่จริงหรือคลิปเป็นชุดทดสอบใหม่ที่เป็นอิสระ')),
          ]),
    ]);
  }
}
