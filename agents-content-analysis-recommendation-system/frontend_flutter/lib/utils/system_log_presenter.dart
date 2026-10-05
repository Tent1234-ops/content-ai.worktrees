import 'dart:convert';

String systemLogActorLabel(int? userId, String detail) {
  if (userId != null) return 'ผู้ใช้หมายเลข $userId';
  try {
    final data = jsonDecode(detail);
    if (data is Map && data['deleted_actor_user_id'] is num) {
      return 'ผู้ใช้หมายเลข ${data['deleted_actor_user_id']} (ลบบัญชีแล้ว)';
    }
  } on FormatException {
    // Older audit rows also contain plain text details.
  }
  return 'ระบบอัตโนมัติ';
}

String systemLogActionLabel(String action) {
  if (action == 'admin_dataset_restore') return 'กู้คืน Dataset จากถังขยะ';
  switch (action.trim().toLowerCase()) {
    case 'classification_presentation_activate':
      return 'เปิดโมเดลชั่วคราวสำหรับสาธิต โดยรับทราบว่ายังไม่ผ่านเกณฑ์';
    case 'classification_presentation_disable':
      return 'ปิดโมเดลสาธิตและคืนโมเดลเดิม';
    case 'admin_user_create':
      return 'เพิ่มบัญชีผู้ใช้โดยผู้ดูแล';
    case 'admin_user_update':
      return 'เปลี่ยนข้อมูล สิทธิ์ หรือสถานะบัญชีผู้ใช้';
    case 'admin_user_sessions_revoke':
      return 'บังคับบัญชีผู้ใช้ออกจากระบบทุกเซสชัน';
    case 'admin_user_delete':
      return 'ลบบัญชีผู้ใช้และข้อมูลส่วนตัวที่บันทึก';
    case 'admin_user_file_cleanup':
      return 'ลบบัญชีแล้ว แต่ยังมีไฟล์อัปโหลดที่ลบไม่สำเร็จ';
    case 'notebooklm_candidate_created':
      return 'นำ Transcript เข้าคิวตรวจสอบ';
    case 'dataset_review_approve':
      return 'อนุมัติข้อมูลฝึกเข้าสู่ฐานข้อมูล';
    case 'dataset_review_reject':
      return 'ปฏิเสธข้อมูลฝึกก่อนนำเข้าฐานข้อมูล';
    case 'admin_dataset_create':
      return 'เพิ่มข้อมูล Dataset โดยผู้ดูแล';
    case 'admin_dataset_update':
      return 'แก้ไขข้อมูล Dataset';
    case 'admin_dataset_delete':
      return 'ลบ Dataset ออกจากการใช้งาน โดยเก็บหลักฐานเดิม';
    case 'admin_trend_schedule_update':
      return 'เปลี่ยนรอบอัปเดตเทรนด์อัตโนมัติ';
    case 'trend_scheduled_collection':
      return 'เก็บเทรนด์ตามตารางเวลารายวัน';
    case 'reference_statistics_refresh':
      return 'อัปเดตสถิติคลิปอ้างอิงและเก็บประวัติ';
    case 'reference_statistics_settings_update':
      return 'เปลี่ยนรอบเก็บสถิติและงบคำขอคลิปอ้างอิง';
    case 'admin_dataset_training_content_corrected':
      return 'แก้ไข Transcript หรือหมวดข้อมูลฝึกที่อนุมัติแล้ว';
    case 'admin_settings_update':
      return 'แก้ไขการตั้งค่าระบบ';
    case 'admin_analysis_settings_update':
      return 'แก้ไขความยาวอัปโหลด รุ่น Whisper หรือช่วงเปิดคลิป';
    case 'admin_settings_reset':
      return 'คืนค่าตั้งต้นของระบบ';
    case 'admin_settings_backup':
      return 'สำรองการตั้งค่าระบบ';
    case 'admin_settings_restore':
      return 'กู้คืนการตั้งค่าระบบ';
    case 'video_analyze_save':
      return 'บันทึกผลวิเคราะห์วิดีโอ';
    case 'clip_revision_plan_save':
      return 'บันทึกแผนปรับคลิป (ยังไม่ใช่การปรับเสร็จ)';
    case 'nlp_extract_save':
      return 'บันทึกผลสกัดคำสำคัญ';
    case 'classification_model_smoke_test':
      return 'ทดสอบขั้นตอนฝึกโมเดลเบื้องต้น';
    case 'classification_model_benchmark':
      return 'ฝึกและประเมินโมเดลจำแนกหมวด';
    case 'dataset_scope_holdout_plan_applied':
      return 'บันทึกแผนแบ่งข้อมูลปรับเกณฑ์และทดสอบตามช่อง';
    case 'classification_training_requested':
      return 'เริ่มรอบเทรนโมเดลจากหน้า Admin';
    case 'classification_training_completed':
      return 'เทรนและบันทึกผลประเมินเรียบร้อย';
    case 'classification_training_failed':
      return 'รอบเทรนโมเดลไม่สำเร็จ';
    case 'classification_training_interrupted':
      return 'รอบเทรนโมเดลหยุดกลางทาง';
    case 'classification_model_activate':
      return 'เปิดใช้งานโมเดลจำแนกหมวด';
    case 'youtube_trends_sync':
      return 'อัปเดตข้อมูลเทรนด์ YouTube';
    case 'google_trends_sync':
      return 'อัปเดตข้อมูลเทรนด์ Google';
    case 'tiktok_trends_sync':
      return 'อัปเดตข้อมูลเทรนด์ TikTok';
    case 'trending_fetcher_loop':
      return 'ตัวเก็บเทรนด์รอบหลักทำงานผิดพลาด';
    case 'youtube_category_trend_fetcher_loop':
      return 'ตัวเก็บเทรนด์ YouTube รายหมวดทำงานผิดพลาด';
    case 'purge_legacy_demo_dataset':
      return 'ล้างข้อมูลตัวอย่างรุ่นเก่า';
    case 'kmeans_save':
      return 'บันทึกผลจัดกลุ่ม K-means';
    case 'hdbscan_save':
      return 'บันทึกผลจัดกลุ่ม HDBSCAN';
  }

  final normalized = action.trim().toLowerCase();
  if (normalized.startsWith('trending_fetch_')) {
    final source = normalized.substring('trending_fetch_'.length);
    return 'ดึงข้อมูลเทรนด์ $source ไม่สำเร็จ';
  }
  return action.trim().isEmpty ? 'เหตุการณ์ที่ไม่ระบุชื่อ' : action;
}

String systemLogStatusLabel(String status) {
  switch (status.trim().toLowerCase()) {
    case 'success':
      return 'สำเร็จ';
    case 'failed':
      return 'ไม่สำเร็จ';
    case 'error':
      return 'เกิดข้อผิดพลาด';
    case 'running':
      return 'กำลังทำงาน';
    case 'warning':
      return 'ควรตรวจสอบ';
    default:
      return status.trim().isEmpty ? 'ไม่ทราบสถานะ' : status;
  }
}

String formatSystemLogTimestamp(DateTime? timestamp) {
  if (timestamp == null) return 'ไม่พบเวลา';
  final local = timestamp.toLocal();
  String twoDigits(int value) => value.toString().padLeft(2, '0');
  return '${twoDigits(local.day)}/${twoDigits(local.month)}/${local.year} '
      '${twoDigits(local.hour)}:${twoDigits(local.minute)}:${twoDigits(local.second)}';
}
