import 'package:flutter_test/flutter_test.dart';
import 'package:content_ai_web/models/dataset_review.dart';

void main() {
  test('Unknown has a name and separate validation/test/reserved coverage', () {
    final leaf = DatasetReviewTaxonomyLeaf.fromJson({
      'leaf_key': 'unknown',
      'category_level_1': 'Unknown/Other',
      'category_level_3': null,
      'verified_sample_count': 42,
      'minimum_sample_count': 40,
      'split_counts': {'train': 35, 'validation': 5, 'test': 2},
      'minimum_split_counts': {'validation': 10, 'test': 30},
      'ready': false,
    });
    expect(leaf.displayName, 'นอกขอบเขต');
    expect(leaf.coverageLabels,
        ['นอกขอบเขต 42 คลิป', 'ปรับเกณฑ์ 5/10', 'ทดสอบ 2/30', 'สำรอง 35 คลิป']);
    expect(leaf.ready, isFalse);
  });

  test('Known labels preserve their existing coverage', () {
    final leaf = DatasetReviewTaxonomyLeaf.fromJson({
      'leaf_key': 'phone', 'category_level_3': 'Phone',
      'verified_sample_count': 80, 'minimum_sample_count': 30, 'ready': true,
    });
    expect(leaf.coverageLabels, ['Phone 80/30']);
  });
}
