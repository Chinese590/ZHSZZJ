from pathlib import Path

import numpy as np
from PIL import Image

from app.ai_assist import DinoOnnxSimilarity


class FakeInput:
    name = "pixel_values"


class FakeSession:
    def get_inputs(self):
        return [FakeInput()]

    def run(self, _outputs, feeds):
        batch = feeds["pixel_values"]
        assert batch.shape == (2, 3, 224, 224)
        output = np.zeros((2, 2, 3), dtype=np.float32)
        output[0, 0] = [1.0, 0.0, 0.0]
        output[1, 0] = [1.0, 0.0, 0.0]
        return [output]


def test_onnx_similarity_uses_cls_embedding_and_returns_cosine(tmp_path: Path):
    original = tmp_path / "original.jpg"
    result = tmp_path / "result.jpg"
    Image.new("RGB", (300, 200), (255, 0, 0)).save(original)
    Image.new("RGB", (200, 300), (255, 0, 0)).save(result)

    helper = DinoOnnxSimilarity(session=FakeSession())
    score = helper.compare(original, result)

    assert score == 1.0
