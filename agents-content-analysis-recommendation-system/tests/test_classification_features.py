import io
import unittest

import joblib
import numpy as np
from sqlalchemy import event

from app.services.classification_features import (
    classification_tokens, normalize_classification_text, thai_transcript_features,
)
from scripts.develop_classification_scope import load_development_rows
from tests import test_classification_training as fixtures


class ClassificationFeatureTests(unittest.TestCase):
    def test_thai_spacing_does_not_change_features(self):
        joined = "\u0e17\u0e14\u0e2a\u0e2d\u0e1a\u0e2b\u0e19\u0e49\u0e32\u0e08\u0e2d\u0e41\u0e25\u0e30\u0e41\u0e1a\u0e15\u0e40\u0e15\u0e2d\u0e23\u0e35\u0e48 MacBook Air"
        spaced = "\u0e17\u0e14\u0e2a\u0e2d\u0e1a \u0e2b\u0e19\u0e49\u0e32\u0e08\u0e2d \u0e41\u0e25\u0e30 \u0e41\u0e1a\u0e15\u0e40\u0e15\u0e2d\u0e23\u0e35\u0e48 MacBook Air"
        self.assertEqual(classification_tokens(joined), classification_tokens(spaced))
        features = thai_transcript_features().fit([joined, "optical lens photography"])
        matrix = features.transform([joined, spaced]).toarray()
        np.testing.assert_array_equal(matrix[0], matrix[1])
        self.assertIn("macbook air", features.transformer_list[0][1].vocabulary_)

    def test_preserves_tone_marks_and_latin_boundaries(self):
        text = "\u0e01\u0e49\u0e2d\u0e19 MacBook AIR USB C"
        self.assertEqual(normalize_classification_text(text), "\u0e01\u0e49\u0e2d\u0e19 macbook air usb c")
        self.assertNotEqual(normalize_classification_text("\u0e01\u0e49\u0e2d\u0e19"), normalize_classification_text("\u0e01\u0e2d\u0e19"))

    def test_serialization_preserves_transform_and_no_refit_on_input(self):
        features = thai_transcript_features().fit(["camera lens", "portable computer"])
        buffer = io.BytesIO()
        joblib.dump(features, buffer)
        buffer.seek(0)
        loaded = joblib.load(buffer)
        np.testing.assert_allclose(features.transform(["new product"]).toarray(), loaded.transform(["new product"]).toarray())
        self.assertNotIn("new", loaded.transformer_list[0][1].vocabulary_)

    def test_development_sql_excludes_test_and_reserved_unknown(self):
        fixture = fixtures.ClassificationTrainingTests()
        fixture.setUp()
        try:
            for index, split in enumerate(("train", "validation", "test")):
                fixture._add_example("phone", split, 10 + index)
                fixture._add_example("unknown", split, 20 + index)
            fixture.db.commit()
            statements = []
            def observe(conn, cursor, statement, parameters, context, executemany):
                if statement.startswith("SELECT") and "dataset_contents" in statement:
                    statements.append((statement, parameters))
            event.listen(fixture.engine, "before_cursor_execute", observe)
            train, validation, unknown = load_development_rows(fixture.db)
            self.assertEqual([r.split for r in train], ["train"])
            self.assertEqual([r.split for r in validation], ["validation"])
            self.assertEqual([r.split for r in unknown], ["validation"])
            self.assertEqual(len(statements), 2)
            for sql, parameters in statements:
                self.assertIn("data_split", sql.split("WHERE", 1)[1])
            # Eligibility permits all production splits; the final AND clause
            # must narrow the actual SELECT before rows are materialized.
            self.assertEqual(statements[0][1][-2:], ("train", "validation"))
            self.assertEqual(statements[1][1][-1], "validation")
        finally:
            fixture.tearDown()


if __name__ == "__main__":
    unittest.main()
